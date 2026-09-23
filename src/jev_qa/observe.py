"""Turn the live page into a numbered element table that Jev can choose from.

One browser call reads every visible, enabled control in the viewport, tags it with
`data-jev-idx="<n>"` and returns role, accessible name and current value for each, plus the
visible text. Indices are fresh on every observation: the runner acts on `[data-jev-idx="n"]`
with a plain Playwright locator, so a model answer can only ever point at something the
page really showed. Password fields report "(filled)" or "", never their content.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, Field

TYPE_ROLES = frozenset({"textbox", "searchbox", "combobox"})
# Fields are typed into, not clicked: clicking them only focuses, which is noise in the menu.
NO_CLICK_ROLES = frozenset({"textbox", "searchbox"})

OBSERVE_JS = r"""
(args) => {
  const { maxElements, maxTextChars } = args;
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  document.querySelectorAll('[data-jev-idx]').forEach(e => e.removeAttribute('data-jev-idx'));
  const SEL = ['a[href]', 'button', 'input', 'select', 'textarea', 'summary', '[role="button"]',
    '[role="link"]', '[role="tab"]', '[role="menuitem"]', '[role="option"]', '[role="checkbox"]',
    '[role="radio"]', '[role="switch"]', '[role="combobox"]', '[role="textbox"]',
    '[role="searchbox"]', '[contenteditable="true"]'].join(',');
  const BUTTON_INPUTS = ['submit', 'button', 'reset', 'image'];
  const vw = innerWidth, vh = innerHeight;
  const roleOf = (el, tag, type) => {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    if (tag === 'a') return 'link';
    if (tag === 'button' || tag === 'summary') return 'button';
    if (tag === 'select') return 'select';
    if (tag === 'textarea' || el.isContentEditable) return 'textbox';
    if (tag === 'input') {
      const OWN_ROLE = ['checkbox', 'radio', 'submit', 'button', 'file', 'range', 'reset', 'image'];
      if (OWN_ROLE.includes(type)) return type;
      if (type === 'search') return 'searchbox';
      if (el.hasAttribute('list')) return 'combobox';
      return 'textbox';
    }
    return 'clickable';
  };
  const valueOf = (el, tag, type) => {
    if (tag === 'input') {
      if (['checkbox', 'radio', 'file', ...BUTTON_INPUTS].includes(type)) return '';
      if (type === 'password') return el.value ? '(filled)' : '';
      return String(el.value || '').slice(0, 60);
    }
    if (tag === 'textarea') return String(el.value || '').slice(0, 60);
    if (tag === 'select') {
      const o = el.options[el.selectedIndex];
      return o ? clean(o.text).slice(0, 60) : '';
    }
    if (el.isContentEditable) return clean(el.innerText).slice(0, 60);
    return '';
  };
  const elements = [];
  for (const el of document.querySelectorAll(SEL)) {
    if (elements.length >= maxElements) break;
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'input' && type === 'hidden') continue;
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    if (r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    if (cs.pointerEvents === 'none') continue;
    const formControl = tag === 'input' || tag === 'select' || tag === 'textarea';
    if (cs.opacity === '0' && !formControl) continue;
    // Covered by a modal, banner or overlay? Then a person could not click it either.
    const cx = Math.min(vw - 1, Math.max(0, r.left + r.width / 2));
    const cy = Math.min(vh - 1, Math.max(0, r.top + r.height / 2));
    const top = document.elementFromPoint(cx, cy);
    if (top && top !== el && !el.contains(top) && !top.contains(el)) {
      const label = top.closest('label');
      if (!(label && label.control === el)) continue;
    }
    const role = roleOf(el, tag, type);
    const editable = formControl || el.isContentEditable;
    const text = editable ? '' : clean(el.innerText || el.textContent).slice(0, 80);
    const labelText = el.labels && el.labels.length ? clean(el.labels[0].innerText) : '';
    const caption = tag === 'input' && BUTTON_INPUTS.includes(type) ? el.value : '';
    const attr = a => el.getAttribute(a);
    const name = clean(attr('aria-label') || labelText || attr('placeholder') ||
      el.getAttribute('title') || el.getAttribute('alt') || caption || text ||
      el.getAttribute('name') || el.id || '').slice(0, 80);
    let checked = null;
    if (type === 'checkbox' || type === 'radio') checked = !!el.checked;
    else if (el.hasAttribute('aria-checked')) checked = el.getAttribute('aria-checked') === 'true';
    el.setAttribute('data-jev-idx', String(elements.length + 1));
    elements.push({ idx: elements.length + 1, role, name, value: valueOf(el, tag, type), checked });
  }
  // Visible text, viewport first, so a toast or heading is never crowded out by a long footer.
  const inView = [], rest = [];
  let length = 0;
  if (document.body) {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    let node;
    while (length < maxTextChars && (node = walker.nextNode())) {
      const raw = node.textContent;
      if (!raw || !raw.trim()) continue;
      const parent = node.parentElement;
      if (!parent || parent.closest('script, style, noscript, template')) continue;
      const opts = { checkOpacity: true, checkVisibilityCSS: true };
      if (parent.checkVisibility && !parent.checkVisibility(opts)) continue;
      range.selectNodeContents(node);
      const r = range.getBoundingClientRect();
      if (r.width <= 0 && r.height <= 0) continue;
      const value = clean(raw);
      if (r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw) {
        inView.push(value); length += value.length + 1;
      }
      else rest.push(value);
    }
  }
  const text = (inView.join('\n') + '\n' + rest.join('\n')).trim().slice(0, maxTextChars);
  const height = document.documentElement.scrollHeight;
  return { url: location.href, title: document.title, text, elements,
    can_scroll_down: scrollY + vh < height - 2, can_scroll_up: scrollY > 0 };
}
"""


class Element(BaseModel):
    idx: int
    role: str
    name: str = ""
    value: str = ""
    checked: bool | None = None

    @property
    def typable(self) -> bool:
        return self.role in TYPE_ROLES

    @property
    def clickable(self) -> bool:
        return self.role not in NO_CLICK_ROLES

    def describe(self) -> dict[str, Any]:
        d: dict[str, Any] = {"element": f"[{self.idx}] {self.role} '{self.name}'"}
        if self.value:
            d["current_value"] = self.value
        if self.checked is not None:
            d["checked"] = self.checked
        return d


class Observation(BaseModel):
    url: str
    title: str = ""
    text: str = ""
    elements: list[Element] = Field(default_factory=list)
    can_scroll_down: bool = False
    can_scroll_up: bool = False

    @property
    def clickable(self) -> list[Element]:
        return [e for e in self.elements if e.clickable]

    @property
    def typable(self) -> list[Element]:
        return [e for e in self.elements if e.typable]

    def element(self, idx: int) -> Element:
        return next(e for e in self.elements if e.idx == idx)


async def observe(page: Any, *, max_elements: int = 100, max_text_chars: int = 4000) -> Observation:
    """One atomic snapshot of the current page (Playwright async `Page`)."""
    raw = await page.evaluate(
        OBSERVE_JS, {"maxElements": max_elements, "maxTextChars": max_text_chars}
    )
    return Observation.model_validate(raw)


def mask(text: str, secrets: Iterable[str]) -> str:
    """Replace every secret value that leaked into page text or a trace with a placeholder."""
    for value in secrets:
        if value:
            text = text.replace(value, "<secret>")
    return text

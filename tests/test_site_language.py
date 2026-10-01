"""Exercise the shipped language script, including old English preferences."""

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_site_defaults_to_chinese_and_english_requires_explicit_selection():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute the website script")
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
function load(search, storage) {
  const buttons = ['zh', 'en'].map(language => ({
    dataset: {language}, attributes: {},
    setAttribute(key, value) { this.attributes[key] = value; },
    addEventListener(event, callback) { this.click = callback; }
  }));
  const document = {
    documentElement: {},
    querySelector() { return {}; },
    querySelectorAll(selector) {
      return selector === '[data-language]' ? buttons : [];
    }
  };
  const window = {
    location: {search, href: 'https://example.test/' + search},
    history: {replaceState(state, title, url) { window.url = String(url); }}
  };
  vm.runInNewContext(source, {document, window, localStorage: storage,
    URL, URLSearchParams});
  return {document, window, buttons};
}
const oldEnglish = {getItem() { return 'en'; }, setItem() {}};
const blockedStorage = {
  getItem() { throw Error('Storage blocked'); },
  setItem() { throw Error('Storage blocked'); }
};
for (const storage of [oldEnglish, blockedStorage]) {
  const page = load('', storage);
  assert.equal(page.document.documentElement.lang, 'zh-CN');
  assert.equal(page.buttons[0].attributes['aria-pressed'], 'true');
  page.buttons[1].click();
  assert.equal(page.document.documentElement.lang, 'en');
  assert.equal(new URL(page.window.url).searchParams.get('lang'), 'en');
  page.buttons[0].click();
  assert.equal(page.document.documentElement.lang, 'zh-CN');
  assert.equal(new URL(page.window.url).searchParams.has('lang'), false);
  assert.equal(load('', storage).document.documentElement.lang, 'zh-CN');
}
assert.equal(load('?lang=en', oldEnglish).document.documentElement.lang, 'en');
assert.equal(load('?lang=invalid', oldEnglish).document.documentElement.lang, 'zh-CN');
"""
    subprocess.run(
        [node, "-e", script, str(ROOT / "site" / "app.js")],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )

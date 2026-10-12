"""Run the real demo clock through pause, visibility and repeated playback."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_demo_uses_elapsed_frames_and_freezes_when_paused_or_hidden():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node required for the actual website clock")
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const listeners = {};
let now=0, next=0, frames=new Map();
function element() { return {textContent:'',dataset:{},style:{},scrollWidth:180,clientWidth:680,
 getBoundingClientRect(){return {width:180}},setAttribute(){}, addEventListener(name,fn){this[name]=fn;}}; }
const nodes=Object.fromEntries(['.live-demo','#demo-transcript','#demo-output','#demo-status','#demo-pause','.demo-window','.demo-capsule'].map(k=>[k,element()]));
const document={hidden:false,documentElement:{lang:'zh-CN'},querySelector(s){return s.startsWith('meta[')?{}:nodes[s]||null;},querySelectorAll(){return [];},addEventListener(k,fn){listeners[k]=fn;}};
const motion={matches:false,addEventListener(){}};
const window={matchMedia(){return motion},location:{search:'',href:'https://example.test/'},history:{replaceState(){}},addEventListener(){}};
const ctx={document,window,URL,URLSearchParams,performance:{now:()=>now},requestAnimationFrame(fn){const id=++next;frames.set(id,fn);return id;},cancelAnimationFrame(id){frames.delete(id)},clearInterval(){},setInterval(){}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
function advance(ms){for(let i=0;i<ms;i+=16){now+=16;const work=[...frames.values()];frames.clear();work.forEach(fn=>fn(now));}}
advance(1200);
assert.equal(nodes['.live-demo'].dataset.state,'speaking');
assert(nodes['#demo-transcript'].textContent.length>5);
const before=nodes['#demo-transcript'].textContent;
nodes['#demo-pause'].click();advance(1000);
assert.equal(nodes['#demo-transcript'].textContent,before);
nodes['#demo-pause'].click();advance(160);
assert(nodes['#demo-transcript'].textContent.length>before.length);
vm.runInNewContext('demoElapsed = demoDuration() - 320; renderDemo()',ctx);
assert.equal(nodes['.live-demo'].dataset.state,'delivering');
nodes['#demo-pause'].click();
const fade=nodes['.demo-capsule'].style.opacity;
advance(1000);assert.equal(nodes['.demo-capsule'].style.opacity,fade);
assert.equal(nodes['.live-demo'].dataset.state,'delivering');
nodes['#demo-pause'].click();
document.hidden=true;listeners.visibilitychange();const hidden=nodes['#demo-transcript'].textContent;advance(1200);
assert.equal(nodes['#demo-transcript'].textContent,hidden);
assert.equal(nodes['.demo-capsule'].style.opacity,fade);
document.hidden=false;listeners.visibilitychange();advance(400);
assert.equal(nodes['.live-demo'].dataset.state,'done');
assert.equal(nodes['#demo-output'].textContent,vm.runInNewContext('demoCopy().demoText',ctx));
assert.equal(nodes['#demo-pause'].disabled,false);
nodes['#demo-pause'].click();advance(2000);
assert.equal(nodes['.live-demo'].dataset.state,'done');
assert.equal(frames.size,0);
nodes['#demo-pause'].click();advance(1600);
assert.equal(nodes['.live-demo'].dataset.state,'ready');
assert.equal(nodes['#demo-output'].textContent,vm.runInNewContext('demoCopy().demoPlaceholder',ctx));
advance(1200);assert.equal(nodes['.live-demo'].dataset.state,'speaking');
advance(vm.runInNewContext('demoDuration() + 1600',ctx));
assert.equal(nodes['.live-demo'].dataset.state,'speaking');
assert.equal(frames.size,1);
motion.matches=true;vm.runInNewContext('resetDemo()',ctx);advance(12000);
assert.equal(nodes['.live-demo'].dataset.state,'done');
assert.equal(frames.size,0);
assert.equal(nodes['#demo-pause'].disabled,true);
"""
    subprocess.run([node, "-e", script, str(Path(__file__).resolve().parents[1]/"site/app.js")],
                   check=True,capture_output=True,text=True,timeout=15)


def test_demo_has_no_replay_control():
    site = Path(__file__).resolve().parents[1] / "site"
    assert 'id="demo-replay"' not in (site / "index.html").read_text(encoding="utf-8")
    assert "demoReplay" not in (site / "app.js").read_text(encoding="utf-8")

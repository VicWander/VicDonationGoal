"""Renderer/OBS checks with HTTP interception only: no server or project writes."""
from pathlib import Path
import json
import unittest
from playwright.sync_api import sync_playwright, Error

PUBLIC = Path(__file__).resolve().parents[1] / 'core/public'
ORIGIN = 'http://widget-fixture.test'

class WidgetRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = sync_playwright().start()
        try:
            cls.browser = cls.p.chromium.launch(headless=True)
        except Error:
            cls.browser = cls.p.chromium.launch(channel='msedge', headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.p.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.requests = []
        self.active = {'ok': True, 'revision': 0, 'document': None}
        self.state = {'current': 25, 'goal': 100, 'title': 'Fixture', 'currency': 'RUB'}
        self.fail_active = False
        def route(request_route):
            request = request_route.request
            self.requests.append(request.method)
            path = request.url.split(ORIGIN)[-1].split('?')[0]
            if path == '/api/state':
                request_route.fulfill(json=self.state)
            elif path == '/api/widget/active':
                request_route.fulfill(status=503 if self.fail_active else 200, json=self.active)
            elif path in ['/widget.html', '/widget.js', '/style.css', '/widget-model.js', '/widget-presets.js', '/widget-renderer.js', '/widget-renderer.css']:
                request_route.fulfill(path=str(PUBLIC / path.lstrip('/')))
            else:
                request_route.fulfill(status=404, body='')
        self.context.route('**/*', route)

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.assertTrue(all(method == 'GET' for method in self.requests))
        self.context.close()

    def load_renderer(self):
        self.page.goto(ORIGIN + '/widget.html')
        self.page.evaluate("""async () => {
          await new Promise((resolve,reject)=>{const s=document.createElement('script');s.src='/widget-presets.js';s.onload=resolve;s.onerror=reject;document.head.append(s)});
        }""")

    def test_eight_presets_format_text_conditions_and_stable_nodes(self):
        self.load_renderer()
        result = self.page.evaluate("""() => {
          const M=VDGWidgetModel, R=VDGWidgetRenderer, host=document.createElement('div');document.body.append(host);
          const ids=VDGWidgetPresets.list().map(p=>p.id);
          for(const id of ids){const d=VDGWidgetPresets.create(id),r=R.mount(host,d,{animate:false});r.update({current:50,goal:100,title:'<img id=xss>'});if(host.querySelectorAll('[data-widget-element]').length!==d.elements.length)throw Error(id);r.destroy()}
          const d=M.createDocument(),e=M.createElement('text');e.text='{{title}} {{current}} {{currency}} {{lastName}}';e.condition={enabled:true,metric:'percent',op:'gte',value:50,action:'show',color:'@primary'};d.elements.push(e);
          const r=R.mount(host,d,{animate:false});r.update({current:25,goal:100});const node=host.querySelector('[data-widget-element]'),hidden=node.hidden;
          r.update({current:75,goal:100,title:'<img id=xss>',currency:'RUB',lastName:'Vic'});
          const stable=node===host.querySelector('[data-widget-element]'),escaped=!host.querySelector('#xss'),text=node.textContent;
          const output={ids,hidden,visible:!node.hidden,stable,escaped,text,formatted:R.format('{{current}} {{currency}}',{current:12.349,currency:'RUB'},{decimals:2,rounding:'floor',currency:'none'})};r.destroy();return output;
        }""")
        self.assertEqual(len(result['ids']), 8)
        for key in ['hidden', 'visible', 'stable', 'escaped']:
            self.assertTrue(result[key], key)
        self.assertIn('Vic', result['text'])
        self.assertEqual(result['formatted'], '12,34 ')

    def test_progress_variants_and_custom_opaque_bridge(self):
        self.load_renderer()
        result = self.page.evaluate("""async () => {
          const M=VDGWidgetModel,d=M.createDocument();d.width=1000;d.height=800;
          for(const shape of ['bar','ring','arc','segments','mask']){const e=M.createElement('progress');e.progress.shape=shape;e.width=200;e.height=100;e.y=d.elements.length*110;d.elements.push(e)}
          const code=M.createElement('custom');code.custom.html='<b data-vdg-text="title"></b><i data-vdg-field="caption"></i>';code.custom.fields=[{key:'caption',label:'Caption',type:'text',default:'default'}];code.custom.values={caption:'local'};
          code.custom.js=`addEventListener('vdg:update',e=>{let blocked=false;try{parent.document.body}catch(_){blocked=true}parent.postMessage({fixture:true,blocked,text:document.body.textContent,keys:Object.keys(e.detail.state)},'*')})`;d.elements.push(code);
          const host=document.createElement('div');document.body.append(host);
          const received=new Promise(resolve=>addEventListener('message',function on(e){if(e.data&&e.data.fixture){removeEventListener('message',on);resolve(e.data)}}));
          window.fixtureRenderer=VDGWidgetRenderer.mount(host,d,{animate:false,editor:true});fixtureRenderer.update({title:'Safe',current:50,goal:100,adminSecret:'NO'});
          const payload=await received;
          return {...payload,sandbox:host.querySelector('iframe').getAttribute('sandbox'),graphics:host.querySelectorAll('svg').length,rectWidth:host.querySelector('svg rect:last-child').getAttribute('width')};
        }""")
        self.assertTrue(result['blocked'])
        self.assertEqual(result['sandbox'], 'allow-scripts')
        self.assertIn('Safelocal', result['text'])
        self.assertNotIn('adminSecret', result['keys'])
        self.assertEqual(result['graphics'], 5)
        self.assertEqual(float(result['rectWidth']), 100)

    def test_obs_preserves_legacy_until_apply_and_keeps_active_node(self):
        self.load_renderer()
        self.assertTrue(self.page.locator('#legacyWidget').is_visible())
        doc = self.page.evaluate("VDGWidgetPresets.create('classic')")
        self.active = {'ok': True, 'revision': 1, 'document': doc}
        self.page.wait_for_function("!document.getElementById('designedWidget').hidden")
        self.page.evaluate("window.originalNode=document.querySelector('[data-widget-element]')")
        self.active['revision'] = 2 # draft-only save must not rebuild the active document
        self.state['current'] = 75
        self.page.wait_for_timeout(850)
        self.assertTrue(self.page.evaluate("originalNode===document.querySelector('[data-widget-element]')"))
        self.fail_active = True
        self.page.wait_for_timeout(850)
        self.assertTrue(self.page.evaluate("originalNode===document.querySelector('[data-widget-element]')"))
        self.fail_active = False
        self.active = {'ok': True, 'revision': 3, 'document': None}
        self.page.wait_for_function("!document.getElementById('legacyWidget').hidden")

    def test_smooth_retarget_and_event_replay_suppression(self):
        self.load_renderer()
        self.page.evaluate("""() => {
          const d=VDGWidgetModel.createDocument(),e=VDGWidgetModel.createElement('progress');e.width=200;e.height=40;e.animation={duration:400,easing:'linear',event:'donation',effect:'pulse',threshold:50,intensity:1};d.elements.push(e);
          const host=document.createElement('div');host.id='motion-fixture';document.body.append(host);
          window.motionRenderer=VDGWidgetRenderer.mount(host,d,{animate:true});motionRenderer.update({current:0,goal:100},{event:'donation'});
        }""")
        self.assertEqual(self.page.locator('#motion-fixture').evaluate('(e)=>e.getAnimations({subtree:true}).length'), 0)
        self.page.evaluate("motionRenderer.update({current:100,goal:100},{event:'donation'})")
        self.page.wait_for_timeout(110)
        before = self.page.locator('#motion-fixture svg rect:last-child').get_attribute('width')
        self.page.evaluate("motionRenderer.update({current:50,goal:100})")
        after = self.page.locator('#motion-fixture svg rect:last-child').get_attribute('width')
        self.assertLess(abs(float(before)-float(after)), 12)
        self.page.wait_for_timeout(450)
        self.assertAlmostEqual(float(self.page.locator('#motion-fixture svg rect:last-child').get_attribute('width')), 100, delta=1)
        self.page.evaluate("motionRenderer.update({current:100,goal:100})")
        self.assertEqual(self.page.locator('#motion-fixture').evaluate('(e)=>e.getAnimations({subtree:true}).length'), 0)

    def test_custom_numbers_and_unchanged_updates(self):
        self.load_renderer()
        self.page.evaluate("""()=>{const d=VDGWidgetModel.createDocument(),e=VDGWidgetModel.createElement('custom');
          e.custom.html='<b data-vdg-text="percent"></b><i data-vdg-text="current"></i>';
          e.custom.js="window.updates=0;addEventListener('vdg:update',e=>{window.updates++;window.rawPercent=e.detail.state.percent;})";
          d.elements=[e];const host=document.createElement('div');host.id='customNumberFixture';document.body.append(host);
          window.numberRenderer=VDGWidgetRenderer.mount(host,d,{animate:false});
          numberRenderer.update({current:.58,goal:1});}
        """)
        frame=self.page.locator('#customNumberFixture iframe').element_handle().content_frame()
        frame.wait_for_function('window.rawPercent!==undefined')
        self.assertEqual(frame.locator('b').inner_text(),'58')
        self.assertLess(frame.evaluate('rawPercent'),58)
        before=frame.evaluate('updates')
        self.page.evaluate("()=>{for(let i=0;i<5;i++)numberRenderer.update({current:.58,goal:1});numberRenderer.update({current:.59,goal:1});}")
        frame.wait_for_function('rawPercent===59')
        self.assertEqual(frame.evaluate('updates'),before+1)

    def test_motion_uses_fractional_time_and_does_not_restart_same_target(self):
        self.page.emulate_media(reduced_motion='no-preference')
        self.load_renderer()
        self.page.evaluate("""()=>{const d=VDGWidgetModel.createDocument(),e=VDGWidgetModel.createElement('custom');e.custom.html='<b>Motion</b>';d.elements=[e];const host=document.createElement('div');host.id='motionFixture';document.body.append(host);window.motionRenderer=VDGWidgetRenderer.mount(host,d);}""")
        frame=self.page.locator('#motionFixture iframe').element_handle().content_frame()
        self.assertEqual(frame.evaluate('typeof window.VDGMotion'),'object')
        result=frame.evaluate("""async()=>{let samples=[],timer;const started=performance.now();return await new Promise(resolve=>{const update=value=>{samples.push(value);if(value===1){clearInterval(timer);resolve({samples,elapsed:performance.now()-started});}};VDGMotion.value('fill',0,{initial:0,update});VDGMotion.value('fill',1,{duration:200,update});timer=setInterval(()=>VDGMotion.value('fill',1,{duration:200,update}),16);});}""")
        self.assertGreater(len(result['samples']),5)
        self.assertTrue(any(0<x<1 for x in result['samples']))
        self.assertLess(result['elapsed'],450)

    def test_pause_freezes_custom_css_frames_and_timers(self):
        self.page.emulate_media(reduced_motion='no-preference')
        self.load_renderer()
        self.page.evaluate("""()=>{const d=VDGWidgetModel.createDocument(),e=VDGWidgetModel.createElement('custom');e.custom.html='<b>Pause</b>';e.custom.css='b{display:block;animation:move 2s linear infinite}@keyframes move{from{transform:translateX(0)}to{transform:translateX(100px)}}';e.custom.js='window.framesCount=0;window.timerCount=0;function loop(){framesCount++;requestAnimationFrame(loop)}requestAnimationFrame(loop);setInterval(()=>timerCount++,25)';d.elements=[e];const host=document.createElement('div');host.id='pauseCustom';document.body.append(host);window.pauseRenderer=VDGWidgetRenderer.mount(host,d,{editor:true});}""")
        frame=self.page.locator('#pauseCustom iframe').element_handle().content_frame()
        frame.evaluate("""()=>{const holder=document.createElement('div');holder.innerHTML='<svg xmlns="http://www.w3.org/2000/svg" width="100" height="20"><rect width="10" height="10"><animate attributeName="x" from="0" to="90" dur="2s" repeatCount="indefinite"/></rect></svg>';document.body.append(holder);}""")
        for _ in range(75):
            if frame.evaluate('()=>window.framesCount>2&&window.timerCount>1'):break
            self.page.wait_for_timeout(20)
        self.assertTrue(frame.evaluate('()=>window.framesCount>2&&window.timerCount>1'))
        self.page.evaluate('pauseRenderer.setPaused(true)')
        for _ in range(75):
            if frame.evaluate("()=>document.documentElement.dataset.vdgPaused==='true'"):break
            self.page.wait_for_timeout(20)
        self.assertEqual(frame.evaluate("()=>document.documentElement.dataset.vdgPaused"),'true')
        before=frame.evaluate("()=>({framesCount,timerCount,transform:getComputedStyle(document.querySelector('b')).transform,now:performance.now(),date:Date.now(),svg:document.querySelector('svg').getCurrentTime()})")
        self.page.wait_for_timeout(150)
        after=frame.evaluate("()=>({framesCount,timerCount,transform:getComputedStyle(document.querySelector('b')).transform,now:performance.now(),date:Date.now(),svg:document.querySelector('svg').getCurrentTime()})")
        self.assertEqual(before,after)
        self.page.evaluate('pauseRenderer.setPaused(false)')
        for _ in range(75):
            if frame.evaluate('(n)=>framesCount>n',before['framesCount']):break
            self.page.wait_for_timeout(20)
        self.assertGreater(frame.evaluate('()=>framesCount'),before['framesCount'])

if __name__ == '__main__':
    unittest.main()

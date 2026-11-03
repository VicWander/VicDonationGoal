"""Regression checks for visual feedback, motion and real optional Home modules."""
import json
import unittest
from pathlib import Path
from playwright.sync_api import expect
import test_studio_browser as baseline


class PolishTests(baseline.StudioBrowserTests):
    def test_goal_theme_hover_and_animated_checkbox(self):
        self.page.emulate_media(reduced_motion='no-preference')
        for family, mode in [('monocrome','dark'),('palette','light'),('vicwander','dark')]:
            self.page.evaluate('(t)=>VDGThemes.apply(t)', {'family':family,'mode':mode,'base':'stone','accent':'red'})
            self.page.wait_for_timeout(220)
            inner=self.page.locator('.studio-goal .goal-preview')
            self.assertIn(inner.evaluate('el=>getComputedStyle(el).backgroundColor'),['rgba(0, 0, 0, 0)','transparent'])
            self.assertEqual(self.page.locator('.studio-goal a').count(),2)
            self.assertGreater(self.page.locator('#goalNumbersPreview strong').count(),0)
            self.page.locator('.status-row').first.hover()
            self.assertEqual(self.page.locator('.status-row').first.evaluate('el=>getComputedStyle(el).textDecorationLine'),'none')
            if family=='vicwander':
                self.assertIn('gradient', self.page.locator('body').evaluate('el=>getComputedStyle(el).backgroundImage'))
                self.assertIn('gradient', self.page.locator('#addDonationButton').evaluate('el=>getComputedStyle(el).backgroundImage'))
            else:
                self.assertEqual(self.page.locator('#addDonationButton').evaluate('el=>getComputedStyle(el).backgroundImage'),'none')
        self.page.locator('#includeInput').uncheck()
        self.assertNotEqual(self.page.locator('#includeInput').evaluate("el=>getComputedStyle(el).transitionDuration"),'0s')
        self.assertNotEqual(self.page.locator('#includeInput').evaluate("el=>getComputedStyle(el,'::after').transitionDuration"),'0s')
        self.page.evaluate("VDGThemes.apply({mode:'dark',family:'monocrome'})")
        self.page.locator('#includeInput').check()
        self.page.wait_for_timeout(200)
        self.assertTrue(self.page.locator('#includeInput').evaluate('el=>getComputedStyle(el).color!==getComputedStyle(el).backgroundColor'),'Checkbox tick must contrast with the checked fill')
        self.navigate('donations/history')
        csv=self.page.locator('a[href*="csv"]').first
        csv.hover()
        self.assertEqual(csv.evaluate('el=>getComputedStyle(el).textDecorationLine'),'none')

    def test_persistent_selection_and_disclosures_animate_once(self):
        self.page.emulate_media(reduced_motion='no-preference')
        self.navigate('donations/history')
        self.page.wait_for_timeout(280)
        self.page.evaluate("window.fixtureMarker=document.querySelector('.studio-subnav-indicator')")
        self.page.locator('.studio-subnav a[href="#donations/top"]').click()
        self.assertTrue(self.page.evaluate("window.fixtureMarker===document.querySelector('.studio-subnav-indicator')"))
        self.assertEqual(self.page.locator('.studio-subnav-indicator').evaluate('el=>getComputedStyle(el).viewTransitionName'),'none')
        self.assertTrue(self.page.locator('.studio-subnav-indicator').evaluate('el=>el.getAnimations().length>0'))
        self.page.wait_for_selector('[data-donor-id] [data-donor-action="expand"]')
        self.page.locator('[data-donor-id] [data-donor-action="expand"]').first.click()
        self.assertTrue(self.page.locator('.donor-card.expanded .donor-detail').first.evaluate('el=>el.getAnimations().length>0'))
        self.page.wait_for_timeout(300)
        self.page.evaluate('renderTop()')
        self.assertEqual(self.page.locator('.donor-card.expanded .donor-detail').first.evaluate('el=>el.getAnimations().length'),0)
        self.navigate('donations/history')
        self.page.locator('[data-action="menu"]').first.click()
        self.assertTrue(self.page.locator('.action-menu.open').first.evaluate('el=>el.getAnimations().length>0'))
        self.page.wait_for_timeout(210)
        self.page.evaluate('renderTable()')
        self.assertEqual(self.page.locator('.action-menu.open').first.evaluate('el=>el.getAnimations().length'),0)

    def test_new_catalog_and_shared_real_forms_survive_routes(self):
        self.page.locator('[data-board-action="edit"]').click()
        self.page.locator('[data-board-action="catalog"]').click()
        dialog=self.page.locator('.dashboard-catalog-dialog')
        expect(dialog).to_be_visible()
        self.assertEqual(dialog.locator('[data-board-action="add"]').count(),12)
        for module in ['rates','ttsQueue','ttsTest','summary','ttsHistory','services']:
            dialog.locator(f'[data-board-action="add"][data-type="{module}"]').click()
        dialog.locator('.catalog-close').click()
        with self.page.expect_response(lambda r:r.url.endswith('/api/ui/settings') and r.request.method=='POST') as response:
            self.page.locator('[data-board-action="save"]').click()
        self.assertEqual(response.value.status,200)
        for module in ['rates','ttsQueue','ttsTest','summary','ttsHistory','services']:
            expect(self.page.locator(f'[data-block="{module}"]')).to_be_visible()
        self.page.locator('#rateUSDInput').fill('123.45')
        self.page.locator('#ttsTestText').fill('Preserved real test input')
        self.navigate('donations/rates')
        expect(self.page.locator('#rateUSDInput')).to_be_visible()
        expect(self.page.locator('#rateUSDInput')).to_have_value('123.45')
        self.navigate('tts/queue')
        expect(self.page.locator('#ttsQueueBody')).to_be_visible()
        expect(self.page.locator('#ttsTestText')).to_have_value('Preserved real test input')
        self.navigate('home/dashboard')
        expect(self.page.locator('[data-block="rates"] #rateUSDInput')).to_have_value('123.45')
        expect(self.page.locator('[data-block="ttsTest"] #ttsTestText')).to_have_value('Preserved real test input')
        for width in [1500,390]:
            self.page.set_viewport_size({'width':width,'height':1000})
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),width+1)

    def test_tts_card_hover_theme_and_empty_row(self):
        fixture_job={'id':'visual-test','username':'Fixture','status':'sent','provider':'speakerbot','voice':'Fixture','createdAt':'2026-10-20T12:00:00Z','originalText':'A test message'}
        self.page.route('**/api/tts/history?*',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps([fixture_job])))
        self.navigate('tts/history')
        self.page.evaluate("""()=>{document.getElementById('ttsPanel').classList.remove('active');ttsHistory=[{id:'visual-test',username:'Fixture',status:'sent',provider:'speakerbot',voice:'Fixture',createdAt:'2026-10-20T12:00:00Z',originalText:'A test message'}];renderHistory();}""")
        self.page.emulate_media(reduced_motion='no-preference')
        row=self.page.locator('.tts-history-summary-row').first
        backgrounds=[]
        for family,mode in [('monocrome','dark'),('palette','light'),('vicwander','dark')]:
            self.page.evaluate('(t)=>VDGThemes.apply(t)',{'family':family,'mode':mode,'base':'stone','accent':'red'})
            self.page.wait_for_timeout(220)
            row.hover()
            self.page.wait_for_timeout(200)
            backgrounds.append(row.evaluate('el=>getComputedStyle(el).backgroundColor'))
            self.assertTrue(row.locator('td').evaluate_all("els=>els.every(el=>['rgba(0, 0, 0, 0)','transparent'].includes(getComputedStyle(el).backgroundColor))"))
            self.assertGreater(float(row.evaluate('el=>parseFloat(getComputedStyle(el).borderRadius)')),0)
            self.assertEqual(row.locator('.danger').evaluate('el=>getComputedStyle(el).boxShadow'),'none')
        self.assertGreater(len(set(backgrounds)),1)
        self.page.locator('[data-history-action="expand"]').first.click()
        detail=self.page.locator('[data-history-detail="visual-test"]')
        self.assertTrue(detail.evaluate('el=>el.getAnimations().length>0'))
        self.page.wait_for_timeout(260)
        self.page.locator('[data-history-action="expand"]').first.click()
        self.assertTrue(detail.evaluate('el=>el.getAnimations().length>0'))
        expect(detail).to_be_hidden()
        self.navigate('tts/queue')
        self.page.evaluate("()=>{document.getElementById('ttsPanel').classList.remove('active');ttsBootstrap.queue=[];renderQueue();}")
        empty=self.page.locator('#ttsQueueBody tr')
        empty.hover()
        self.assertIn(empty.evaluate('el=>getComputedStyle(el).backgroundColor'),['rgba(0, 0, 0, 0)','transparent'])

    def test_home_top_loads_its_unfiltered_ranking(self):
        self.navigate('donations/top')
        self.page.locator('#topDonorsSearch').fill('no fixture matches this')
        self.page.wait_for_timeout(450)
        self.navigate('home/dashboard')
        self.page.locator('[data-board-action="edit"]').click()
        self.page.locator('[data-board-action="catalog"]').click()
        self.page.locator('[data-type="top"][data-board-action="add"]').click()
        self.page.locator('.catalog-close').click()
        self.page.locator('[data-board-action="save"]').click()
        expect(self.page.locator('#studioTop')).to_contain_text('Short Fixture')

    def test_integration_switch_animates_and_late_response_does_not_replace_selection(self):
        self.page.emulate_media(reduced_motion='no-preference')
        self.navigate('integrations/services')
        self.page.wait_for_function("integrationState.detail && !document.querySelector('#integrationDetail').inert")
        ids=self.page.evaluate('integrationState.bootstrap.integrations.map(i=>i.id)')
        self.assertGreaterEqual(len(ids),2)
        first,second=ids[:2]
        self.page.evaluate('(id)=>{void loadIntegrationDetail(id)}',second)
        self.page.wait_for_function('(id)=>integrationState.detail.summary.id===id',arg=second)
        self.assertTrue(self.page.locator('#integrationDetail').evaluate('el=>el.getAnimations().length>0'))
        pending=[]
        def hold(route):
            pending.append(route)
        self.page.route('**/api/integrations/detail?*',hold)
        self.page.evaluate('(ids)=>{void loadIntegrationDetail(ids[0]);void loadIntegrationDetail(ids[1]);}',[first,second])
        self.page.wait_for_timeout(60)
        self.assertEqual(len(pending),2)
        latest=next(r for r in pending if 'id='+second in r.request.url)
        previous=next(r for r in pending if 'id='+first in r.request.url)
        latest.continue_()
        self.page.wait_for_function('(id)=>integrationState.detail.summary.id===id&&!document.querySelector("#integrationDetail").inert',arg=second)
        previous.continue_()
        self.page.wait_for_timeout(120)
        self.assertEqual(self.page.evaluate('integrationState.detail.summary.id'),second)
        self.page.unroute('**/api/integrations/detail?*',hold)
        def fail(route):
            route.fulfill(status=500,content_type='application/json',body='{"error":"Fixture unavailable"}')
        self.page.route('**/api/integrations/detail?*',fail)
        self.page.evaluate('(id)=>{void loadIntegrationDetail(id)}',first)
        self.page.wait_for_function('!document.querySelector("#integrationDetail").inert')
        self.assertEqual(self.page.evaluate('integrationState.selectedId'),second,'Failed selection must not target the old form at a different service')
        self.page.unroute('**/api/integrations/detail?*',fail)

    def test_docs_read_theme_without_saving(self):
        writes=[]
        self.page.on('request',lambda request:writes.append(request.url) if request.method=='POST' else None)
        self.page.goto(self.origin+'/docs/index.html')
        self.page.wait_for_function('window.VDGThemes')
        self.page.evaluate('async()=>await VDGThemes.ready')
        self.assertIn('1.5',self.page.title())
        self.assertEqual(writes,[])
        self.assertNotIn('Руководство v1.4.4',self.page.locator('body').inner_text())


if __name__=='__main__':
    unittest.main()

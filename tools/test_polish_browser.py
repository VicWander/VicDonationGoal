from test_widget_editor_browser import WidgetEditorTests
from playwright.sync_api import expect
class PolishTests(WidgetEditorTests):
 def test_catalog_and_polish(self):
  self.page.goto(self.origin+'/admin.html#guidebook/appearance')
  expect(self.page.locator('[data-menu="guidebook"] .menu-toggle')).to_have_count(0)
  expect(self.page.locator('.guidebook-tile')).to_have_count(2)
  expect(self.page.locator('.guidebook-ai-mark')).to_have_text('AI')
  expect(self.page.locator('[data-guidebook-catalog] h2')).to_have_count(0)
  self.page.goto(self.origin+'/admin.html#widget/obs')
  self.page.locator('#studioObsBackdrop').select_option('dark')
  expect(self.page.locator('.studio-obs iframe')).to_have_attribute('data-backdrop','dark')
  self.page.goto(self.origin+'/admin.html#widget/ai')
  self.assertFalse(self.page.locator('.ai-code-details').evaluate('(e)=>e.open'))
  self.editor()
  self.assertGreaterEqual(float(self.page.locator('.we-editor label').first.evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)')),12)
 def test_all_bases_both_modes_and_store(self):
  self.page.goto(self.origin+'/admin.html#settings/appearance')
  self.page.wait_for_function('window.VDGThemes && !document.querySelector("#studioAppearanceSettings select").disabled')
  bases=self.page.locator('#studioAppearanceSettings select[name="base"] option').evaluate_all('(nodes)=>nodes.map(n=>n.value)')
  self.assertGreater(len(bases),20)
  for mode in ['dark','light']:
   colors=[]
   for base in bases:
    self.page.evaluate('(x)=>VDGThemes.apply({mode:x.mode,family:"palette",base:x.base,accent:"neutral"})',{'mode':mode,'base':base})
    colors.append(self.page.locator('body').evaluate('(e)=>getComputedStyle(e).backgroundColor'))
   self.assertEqual(len(set(colors)),len(bases))
  response=self.page.request.post(self.origin+'/api/ui/settings',data={'theme':{'mode':'light','family':'palette','base':'red','accent':'blue'}})
  self.assertEqual(response.status,200)
  self.page.reload()
  self.page.wait_for_function('VDGThemes.get().base==="red"')

 def test_tts_disclosures_preserve_values(self):
  self.page.goto(self.origin+'/admin.html#tts/profiles')
  self.page.wait_for_function('document.querySelector("#ttsProfileIdInput").value')
  value=self.page.locator('#ttsProfileAliasInput').input_value()
  summary=self.page.get_by_text('Голоса и дополнительные параметры',exact=True)
  summary.click()
  expect(self.page.locator('#ttsProfileAliasInput')).to_be_visible()
  self.assertEqual(self.page.locator('#ttsProfileAliasInput').input_value(),value)
  summary.click()
  self.assertEqual(self.page.locator('#ttsProfileAliasInput').input_value(),value)
  self.page.goto(self.origin+'/admin.html#tts/rules')
  self.page.get_by_text('Условия по зрителю, награде и сумме',exact=True).click()
  expect(self.page.locator('#ttsRuleUserIdsInput')).to_be_visible()

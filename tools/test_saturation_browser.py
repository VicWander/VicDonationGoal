from test_studio_browser import StudioBrowserTests
from playwright.sync_api import expect
class SaturationTests(StudioBrowserTests):
 def test_slider_is_continuous_and_saved(self):
  self.page.goto(self.origin+'/admin.html#settings/appearance')
  self.page.evaluate('async()=>await VDGThemes.ready')
  form=self.page.locator('#studioAppearanceSettings form')
  form.locator('[name="family"]').select_option('palette')
  form.locator('[name="base"]').select_option('red')
  slider=form.locator('[name="baseSaturation"]')
  self.assertEqual(slider.get_attribute('type'),'range')
  for mode in ['dark','light']:
   form.locator('[name="mode"]').select_option(mode)
   samples=[]
   for n in [0,27,63,100]:
    slider.fill(str(n));slider.dispatch_event('input')
    samples.append(self.page.locator('body').evaluate('(e)=>getComputedStyle(e).getPropertyValue("--bg")'))
   self.assertEqual(len(set(samples)),4)
   lights=[sample.split()[0] for sample in samples]
   self.assertEqual(len(set(lights)),1)
  accent=self.page.locator('body').evaluate('(e)=>getComputedStyle(e).getPropertyValue("--accent")')
  slider.fill('47');slider.dispatch_event('input')
  self.assertEqual(self.page.locator('body').evaluate('(e)=>getComputedStyle(e).getPropertyValue("--accent")'),accent)
  form.locator('[data-theme-save]').click()
  expect(form.locator('[data-theme-status]')).to_have_text('Тема сохранена.')
  self.page.reload();self.page.evaluate('async()=>await VDGThemes.ready')
  expect(self.page.locator('#studioAppearanceSettings [name="baseSaturation"]')).to_have_value('47')
 def test_legacy_settings_and_invalid_values(self):
  for value in [-1,101,True,'50',1.5]:
   response=self.page.request.post(self.origin+'/api/ui/settings',data={'theme':{'baseSaturation':value}})
   self.assertNotEqual(response.status,200)
  response=self.page.request.post(self.origin+'/api/ui/settings',data={'theme':{'mode':'light','family':'palette','base':'red','accent':'blue'}})
  self.assertEqual(response.status,200)

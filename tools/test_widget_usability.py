import unittest
from playwright.sync_api import expect
from test_widget_editor_browser import WidgetEditorTests

class UsabilityTests(WidgetEditorTests):
 def test_library_is_a_page_and_edits_share_one_editor(self):
  self.editor()
  self.page.goto(self.origin+'/admin.html#widget/presets')
  expect(self.page.locator('[data-we-library-page]')).to_be_visible()
  expect(self.page.locator('.we-dialog')).not_to_be_visible()
  self.page.locator('[data-we-library-edit="preset:ring"]').locator('xpath=ancestor::details').locator('summary').click()
  self.page.locator('[data-we-library-edit="preset:ring"]').click()
  expect(self.page).to_have_url(self.origin+'/admin.html#widget/editor')
  self.assertEqual(self.page.locator('#widgetEditorRoot').count(),1)
  self.page.get_by_role('button',name='Сохранить вариант',exact=True).click()
  self.page.get_by_role('textbox',name='Название варианта',exact=True).fill('Мой черновик')
  self.page.get_by_role('textbox',name='Название варианта',exact=True).press('Enter')
  expect(self.page.locator('.we-dialog')).not_to_be_visible()
  self.page.goto(self.origin+'/admin.html#widget/presets')
  expect(self.page.locator('[data-we-library-page]')).to_contain_text('Мой черновик')
  self.page.locator('[data-we-library-apply]').first.click()
  expect(self.page.locator('[data-we-library-status]')).to_contain_text('Применено')
 def test_editor_readable_data_and_full_checker(self):
  self.editor()
  self.page.get_by_role('button',name='Текст',exact=True).click()
  expect(self.page.locator('[data-we-token="remaining"]')).to_have_text('Осталось')
  expect(self.page.locator('[data-we-help]').first).to_be_visible()
  self.assertEqual(self.page.locator('.we-viewport').get_attribute('data-preview-background'),'checker')

 def test_library_copy_and_delete_preserve_active(self):
  self.editor()
  self.page.goto(self.origin+'/admin.html#widget/presets')
  self.page.locator('[data-library-copy="preset:line"]').locator('xpath=ancestor::details').locator('summary').click()
  self.page.locator('[data-library-copy="preset:line"]').click()
  expect(self.page).to_have_url(self.origin+'/admin.html#widget/editor')
  self.page.get_by_role('button',name='Применить в OBS',exact=True).click()
  expect(self.page.locator('[data-we-status]')).to_have_text('Применено в OBS')
  before=self.page.request.get(self.origin+'/api/widget/active').json()['document']
  self.page.goto(self.origin+'/admin.html#widget/presets')
  self.page.locator('[data-library-delete]').locator('xpath=ancestor::details').locator('summary').click()
  self.page.locator('[data-library-delete]').click()
  self.page.locator('[data-library-confirm]').click()
  expect(self.page.locator('[data-library-delete]')).to_have_count(0)
  self.assertEqual(before,self.page.request.get(self.origin+'/api/widget/active').json()['document'])
 def test_dashboard_overflow_percent_and_top_flag(self):
  self.page.goto(self.origin+'/admin.html#home/dashboard')
  self.page.evaluate("()=>{cachedState={...cachedState,current:18220,goal:15000};renderState(cachedState,cachedDonations);}")
  expect(self.page.locator('#progressText')).to_have_text('121%')
  self.assertEqual(self.page.locator('#progressFill').evaluate('(el)=>el.style.width'),'100%')
  row=self.page.locator('[data-studio-record]').first
  row.click()
  flag=self.page.locator('[data-studio-top]')
  expect(flag).to_be_visible()
  key=row.get_attribute('data-studio-record')
  original=flag.is_checked()
  flag.set_checked(not original)
  self.page.wait_for_function('(key)=>cachedDonations.find(d=>d.uniqueKey===key)?.includeInTop===false',arg=key) if original else self.page.wait_for_function('(key)=>cachedDonations.find(d=>d.uniqueKey===key)?.includeInTop===true',arg=key)
  self.page.reload();self.page.locator('[data-studio-record="'+key+'"]').click()
  expect(self.page.locator('[data-studio-top]')).to_be_checked(checked=not original)

 def test_dashboard_goal_flag(self):
  self.page.goto(self.origin+'/admin.html#home/dashboard')
  row=self.page.locator('[data-studio-record]').first
  row.click();flag=self.page.locator('[data-studio-goal]');expect(flag).to_be_visible()
  key=row.get_attribute('data-studio-record');original=flag.is_checked();flag.set_checked(not original)
  self.page.wait_for_function('(x)=>cachedDonations.find(d=>d.uniqueKey===x.key)?.includeInGoal===x.value',arg={'key':key,'value':not original})
  self.page.reload();self.page.locator('[data-studio-record="'+key+'"]').click()
  expect(self.page.locator('[data-studio-goal]')).to_be_checked(checked=not original)

 def test_responsive_library_editor_and_help(self):
  for width in [1920,1280,390]:
   self.page.set_viewport_size({'width':width,'height':1000})
   for route in ['widget/presets','widget/editor']:
    self.page.goto(self.origin+'/admin.html#'+route)
    expect(self.page.locator('#widgetEditorRoot' if route.endswith('editor') else '[data-we-library-page]')).to_be_visible()
    self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),width+1)
  self.page.set_viewport_size({'width':1920,'height':1080})
  self.page.goto(self.origin+'/admin.html#widget/editor')
  self.page.get_by_role('button',name='Текст',exact=True).click()
  self.page.locator('[data-we-prop="text"]').focus()
  self.page.keyboard.press('Tab')
  expect(self.page.locator('.we-tooltip')).to_be_visible()
  self.page.goto(self.origin+'/docs/widget-editor.html')
  expect(self.page.get_by_role('heading',name='Создание своего донат-гола')).to_be_visible()
  expect(self.page.locator('main')).to_contain_text('@primary')

 def test_checker_follows_theme_and_help_is_selective(self):
  from pathlib import Path
  self.editor()
  self.page.get_by_role('button',name='Текст',exact=True).click()
  for prop in ['style.fontFamily','style.fontSize','style.fontWeight','style.lineHeight','style.letterSpacing','style.textAlign','style.textTransform','width','height','textFit']:
   expect(self.page.locator('[data-we-prop="'+prop+'"]').locator('xpath=ancestor::div[contains(@class,"we-field")]').locator('[data-we-help]')).to_have_count(0)
  for prop in ['text','style.fill','style.fill2']:
   expect(self.page.locator('[data-we-prop="'+prop+'"]').locator('xpath=ancestor::div[contains(@class,"we-field")]').locator('[data-we-help]')).to_have_count(1)
  colors=[]
  for family,mode in [('monocrome','dark'),('monocrome','light'),('vicwander','dark')]:
   self.page.evaluate('(t)=>VDGThemes.apply(t)',{'family':family,'mode':mode,'base':'neutral','accent':'blue'})
   colors.append(self.page.locator('.we-viewport').evaluate('(el)=>getComputedStyle(el).backgroundColor'))
  self.assertNotEqual(colors[0],colors[1])
  self.assertNotEqual(colors[0],colors[2])

if __name__=='__main__':unittest.main()

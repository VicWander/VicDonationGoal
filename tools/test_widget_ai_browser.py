import unittest
from playwright.sync_api import expect
from test_widget_editor_browser import WidgetEditorTests

class AITests(WidgetEditorTests):
    def ai(self):
        self.page.goto(self.origin+'/admin.html#widget/ai')
        expect(self.page.locator('[data-ai-root]')).to_be_visible()
        self.page.locator('.ai-code-details > summary').click()

    def test_css_preview_save_and_apply(self):
        self.ai()
        self.page.get_by_label('CSS — оформление',exact=True).fill('body{color:white}.vdg-goal{background:#123456}')
        self.page.get_by_role('button',name='Проверить и показать',exact=True).click()
        expect(self.page.locator('[data-ai-preview] iframe')).to_be_attached()
        self.assertIsNone(self.page.request.get(self.origin+'/api/widget/active').json()['document'])
        self.page.get_by_role('button',name='Сохранить вариант',exact=True).click()
        expect(self.page.locator('[data-ai-status]')).to_contain_text('Вариант сохранён')
        self.assertIsNone(self.page.request.get(self.origin+'/api/widget/active').json()['document'])
        self.page.get_by_role('button',name='Применить в OBS',exact=True).click()
        expect(self.page.locator('[data-ai-status]')).to_contain_text('Применено')
        self.assertTrue(self.page.request.get(self.origin+'/api/widget/active').json()['document']['elements'][0]['custom']['css'])

    def test_parse_failure_preserves_code_and_custom_fields(self):
        self.ai()
        self.page.get_by_label('Режим создания',exact=True).select_option('custom')
        answer='```html\n<strong data-vdg-field="caption"></strong><b data-vdg-text="current"></b>\n```\n```css\nbody{color:red}\n```'
        self.page.get_by_label('Ответ нейросети целиком',exact=True).fill(answer)
        self.page.get_by_role('button',name='Разобрать ответ',exact=True).click()
        expect(self.page.get_by_label('CSS — оформление',exact=True)).to_have_value('body{color:red}')
        self.page.get_by_label('Ответ нейросети целиком',exact=True).fill('непонятный ответ')
        self.page.get_by_role('button',name='Разобрать ответ',exact=True).click()
        expect(self.page.get_by_label('CSS — оформление',exact=True)).to_have_value('body{color:red}')
        self.page.get_by_text('Параметры, созданные нейросетью',exact=True).click()
        self.page.get_by_label('Параметры оформления (JSON)',exact=True).fill('[{"key":"caption","label":"Надпись","type":"text","default":"Спасибо"}]')
        self.page.get_by_role('button',name='Проверить и показать',exact=True).click()
        expect(self.page.get_by_label('Надпись',exact=True)).to_have_value('Спасибо')
        self.page.get_by_label('Надпись',exact=True).fill('Привет')
        frame=self.page.locator('[data-ai-preview] iframe').element_handle().content_frame()
        expect(frame.locator('strong')).to_have_text('Привет')

    def test_runtime_error_is_reported_and_code_is_isolated(self):
        self.ai()
        self.page.get_by_label('Режим создания',exact=True).select_option('custom')
        self.page.get_by_label('HTML — элементы виджета',exact=True).fill('<b data-vdg-text="title"></b>')
        self.page.get_by_label('JavaScript — поведение',exact=True).fill('throw new Error("AI fixture failure")')
        self.page.get_by_role('button',name='Проверить и показать',exact=True).click()
        expect(self.page.locator('[data-ai-status]')).to_contain_text('AI fixture failure')
        self.assertEqual(self.page.locator('[data-ai-preview] iframe').get_attribute('sandbox'),'allow-scripts')

    def test_full_html_and_failed_checks(self):
        self.ai()
        self.page.get_by_label('Режим создания',exact=True).select_option('custom')
        self.page.get_by_label('Ответ нейросети целиком',exact=True).fill('```html\n<!doctype html><html><head><style>body{color:white}</style></head><body><strong data-vdg-text="title"></strong><script>document.body.dataset.loaded="yes";</script></body></html>\n```')
        self.page.get_by_role('button',name='Разобрать ответ',exact=True).click()
        expect(self.page.get_by_label('CSS — оформление',exact=True)).to_have_value('body{color:white}')
        self.page.get_by_role('button',name='Проверить и показать',exact=True).click()
        frame=self.page.locator('[data-ai-preview] iframe').element_handle().content_frame()
        expect(frame.locator('strong')).to_have_text('Новый микрофон')
        self.page.get_by_role('button',name='150%',exact=True).click()
        self.page.get_by_label('CSS — оформление',exact=True).fill('это не стили')
        self.page.get_by_role('button',name='Проверить и показать',exact=True).click()
        expect(self.page.locator('[data-ai-status]')).to_contain_text('не найдены правила')
        self.page.get_by_role('button',name='Сохранить вариант',exact=True).click()
        expect(self.page.locator('[data-ai-status]')).to_contain_text('не найдены правила')
        self.assertIsNone(self.page.request.get(self.origin+'/api/widget/active').json()['document'])

    def test_prompt_local_recovery_and_backup(self):
        self.editor()
        self.page.get_by_role('button',name='Текст',exact=True).click()
        self.page.locator('[data-we-prop="text"]').fill('Before AI')
        self.page.locator('[data-we-action="save-draft"]').click()
        expect(self.page.locator('[data-we-status]')).to_have_attribute('data-state','saved')
        self.ai()
        self.page.get_by_label('Как должен выглядеть виджет?',exact=True).fill('Белый неоновый цветок')
        self.page.get_by_role('button',name='Скопировать запрос',exact=True).click()
        prompt=self.page.locator('[data-ai-prompt]').input_value()
        self.assertIn('Белый неоновый цветок',prompt)
        self.assertIn('data-vdg-text',prompt)
        self.assertNotIn('Before AI',prompt)
        self.page.reload()
        expect(self.page.get_by_label('Как должен выглядеть виджет?',exact=True)).to_have_value('Белый неоновый цветок')
        self.page.get_by_role('button',name='Проверить и показать',exact=True).click()
        self.page.get_by_role('button',name='Сохранить вариант',exact=True).click()
        expect(self.page.locator('[data-ai-status]')).to_contain_text('Вариант сохранён')
        saved=self.page.request.get(self.origin+'/api/widget/editor').json()['settings']['saved']
        self.assertTrue(any(any(e['text']=='Before AI' for e in d['elements']) for d in saved))

    def test_themes_and_sizes_have_no_page_overflow(self):
        self.ai()
        for width in [1920,1280,390]:
            self.page.set_viewport_size({'width':width,'height':1000})
            for family,mode in [('monocrome','dark'),('monocrome','light'),('vicwander','dark')]:
                self.page.evaluate('(t)=>VDGThemes.apply(t)',{'family':family,'mode':mode,'base':'neutral','accent':'blue'})
                self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),width+1)

    def test_transparent_frame_matches_its_document_color_scheme(self):
        self.ai()
        self.page.get_by_role('button',name='Проверить и показать',exact=True).click()
        frame=self.page.locator('[data-ai-preview] iframe')
        self.assertEqual(frame.evaluate('(el)=>getComputedStyle(el).colorScheme'),'normal')

    def test_hybrid_layers_survive_editor_and_custom_parameters(self):
        import json
        self.ai()
        self.page.get_by_label('Режим создания',exact=True).select_option('custom')
        design={'format':'vdg-ai/1','document':{'name':'Hybrid','width':760,'height':260,'elements':[
            {'id':'flower','type':'custom','name':'Цветок','x':0,'y':0,'width':220,'height':220,'custom':{'html':'<b data-vdg-field="caption"></b>','css':'b{color:white}','js':'','fields':[{'key':'caption','label':'Подпись цветка','type':'text','default':'Цветок'}],'values':{}}},
            {'id':'title','type':'text','name':'Название','text':'{{title}}','x':250,'y':20,'width':420,'height':50},
            {'id':'percent','type':'text','name':'Процент','text':'{{percent}}%','x':250,'y':90,'width':150,'height':50}]}}
        self.page.get_by_label('Ответ нейросети целиком',exact=True).fill(json.dumps(design,ensure_ascii=False))
        self.page.get_by_role('button',name='Разобрать ответ',exact=True).click()
        expect(self.page.locator('[data-ai-layer-summary]')).to_contain_text('3')
        self.page.get_by_role('button',name='Проверить и показать',exact=True).click()
        self.page.get_by_label('Подпись цветка',exact=True).fill('Мой цветок')
        self.page.get_by_role('button',name='Открыть в редакторе',exact=True).click()
        expect(self.page.locator('[data-we-layer]')).to_have_count(3)
        self.page.locator('[data-we-select="percent"]').click()
        self.page.locator('[data-we-prop="x"]').fill('320')
        self.page.locator('[data-we-prop="x"]').press('Tab')
        self.page.get_by_role('button',name='Сохранить',exact=True).click()
        expect(self.page.locator('[data-we-status]')).to_have_attribute('data-state','saved')
        self.page.reload()
        self.page.locator('[data-we-select="percent"]').click()
        expect(self.page.locator('[data-we-prop="x"]')).to_have_value('320')
        self.page.goto(self.origin+'/admin.html#widget/ai')
        self.page.get_by_role('button',name='Доработать текущий черновик',exact=True).click()
        expect(self.page.locator('[data-ai-layer-summary]')).to_contain_text('3')
        self.page.get_by_role('button',name='Проверить и показать',exact=True).click()
        expect(self.page.get_by_label('Подпись цветка',exact=True)).to_have_value('Мой цветок')

    def test_native_only_answer_and_prompt_contract(self):
        import json
        self.ai()
        self.page.get_by_label('Режим создания',exact=True).select_option('custom')
        self.page.get_by_role('button',name='Скопировать запрос',exact=True).click()
        prompt=self.page.locator('[data-ai-prompt]').input_value()
        self.assertIn('VDGMotion.value',prompt)
        self.assertIn('document.elements',prompt)
        example=prompt.split('Минимальный пример структуры: ',1)[1].split('\nЕсли пользователь',1)[0]
        self.assertEqual(json.loads(example.rstrip('.'))['document']['elements'][0]['type'],'custom')
        answer={'format':'vdg-ai/1','document':{'width':760,'height':220,'elements':[{'id':'only','type':'text','name':'Заголовок','text':'{{title}}','width':600,'height':80}]}}
        self.page.get_by_label('Ответ нейросети целиком',exact=True).fill(json.dumps(answer))
        self.page.get_by_role('button',name='Разобрать ответ',exact=True).click()
        self.page.get_by_role('button',name='Проверить и показать',exact=True).click()
        expect(self.page.locator('[data-ai-preview]')).to_contain_text('Новый микрофон')
        self.page.get_by_role('button',name='Применить в OBS',exact=True).click()
        expect(self.page.locator('[data-ai-status]')).to_contain_text('Применено')

if __name__=='__main__':unittest.main()

ПАТЧ СВЕТЛОЙ/ТЁМНОЙ ТЕМЫ ДЛЯ АДМИНКИ

Что добавляет:
- переключатель темы в админке;
- тёмную и светлую тему;
- сохранение выбора темы в браузере;
- общий акцентный градиент:
  #23489e → #35a9d4 → #3bc7da

Патч мягкий:
- НЕ заменяет текущую админку;
- НЕ трогает server.py;
- НЕ трогает учёт донатов;
- добавляет только 2 файла:
  public/admin-theme.css
  public/admin-theme.js

КАК УСТАНОВИТЬ:

1) Скопируй файлы из папки public в свою папку проекта:
   donation_goal_widget/public/

Должно получиться:
   public/admin-theme.css
   public/admin-theme.js

2) Открой:
   public/admin.html

3) В блоке <head> найди строку:
   <link rel="stylesheet" href="admin.css" />

СРАЗУ ПОСЛЕ НЕЁ добавь:
   <link rel="stylesheet" href="admin-theme.css" />

4) В самом низу файла найди:
   <script src="admin.js"></script>

СРАЗУ ПОСЛЕ НЕЁ добавь:
   <script src="admin-theme.js"></script>

Должно быть так:
   <script src="admin.js"></script>
   <script src="admin-theme.js"></script>

5) Сохрани admin.html.

6) Обнови страницу админки:
   http://127.0.0.1:3333/admin.html

Если кнопка не появилась:
- нажми Ctrl+F5;
- проверь, что файлы лежат именно в public;
- проверь, что строки подключены после admin.css и admin.js.

КАК ОТКАТИТЬ:

Удалить из admin.html две строки:
   <link rel="stylesheet" href="admin-theme.css" />
   <script src="admin-theme.js"></script>

Файлы можно оставить, они не будут использоваться.

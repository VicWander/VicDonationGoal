(function (global) {
  'use strict';
  const M = global.VDGWidgetModel;
  const presets = [
    { id: 'classic', name: 'Классический', description: 'Крупный заголовок и широкая полоса с суммой поверх.' },
    { id: 'line', name: 'Тонкая линия', description: 'Лёгкая композиция с тонкой полосой и раздельными подписями.' },
    { id: 'type', name: 'Типографика', description: 'Большая сумма и выразительный процент без тяжёлой рамки.' },
    { id: 'card', name: 'Карточка', description: 'Спокойная тёмная панель с целью и последним донатом.' },
    { id: 'ring', name: 'Кольцо', description: 'Круговой индикатор с процентом в центре.' },
    { id: 'steps', name: 'Ступени', description: 'Прогресс из отдельных сегментов с отметками пути.' },
    { id: 'vertical', name: 'Вертикальный', description: 'Высокий индикатор для боковой области трансляции.' },
    { id: 'shape', name: 'Фигура', description: 'Яркий геометрический медальон с вертикальным заполнением.' }
  ];
  function create(id) {
    const preset=presets.find(p=>p.id===id)||presets[0], d=M.createDocument(preset.name); d.width=760;d.height=180;
    function node(type,name,x,y,w,h,style,extra) { const e=M.createElement(type);Object.assign(e,{name,x,y,width:w,height:h},extra||{});Object.assign(e.style,style||{});d.elements.push(e);return e; }
    function text(name,value,x,y,w,h,size,style) { return node('text',name,x,y,w,h,Object.assign({fill:'@text',fontSize:size},style),{text:value,textFit:'shrink'}); }
    function bar(name,x,y,w,h,style,progress) { const e=node('progress',name,x,y,w,h,Object.assign({radius:h/2,gradient:true,gradientAngle:45},style));Object.assign(e.progress,progress||{});return e; }
    if(preset.id==='classic') {
      d.width=700;d.height=100;d.palette.primary='#23489e';d.palette.secondary='#3bc7da';d.palette.track='rgba(83, 83, 83, 0.747)';
      text('Название цели','{{title}}',0,0,700,36,30,{fontFamily:'ManropeBlod, Helvetica, Arial, sans-serif',fontWeight:800,textTransform:'uppercase',letterSpacing:.3,fill:'rgba(255,255,255,0.92)',shadowColor:'rgba(0,0,0,0.65)',shadowBlur:8,shadowY:2});
      bar('Прогресс',0,42,700,55,{radius:30});
      text('Собрано и цель','{{current}} / {{goal}} {{currency}}',0,43,700,45,26,{fontFamily:'ManropeBlod, Helvetica, Arial, sans-serif',fontWeight:800,textAlign:'center',fill:'rgba(255,255,255,0.95)',shadowColor:'rgba(0,0,0,0.7)',shadowBlur:8,shadowY:2});
    } else if(preset.id==='line') {
      d.height=130;d.palette.primary='#c3f16b';d.palette.secondary='#69cfa5';
      text('Название цели','{{title}}',24,12,500,36,26,{fontWeight:500});text('Процент','{{percent}}%',610,12,126,36,26,{textAlign:'right'});
      bar('Тонкая полоса',24,59,712,6,{radius:3});text('Собрано','{{current}} {{currency}}',24,80,350,30,20,{fontWeight:500});text('Цель','из {{goal}} {{currency}}',390,80,346,30,20,{fill:'#a1a9b7',textAlign:'right',fontWeight:400});
    } else if(preset.id==='type') {
      d.height=240;d.palette.primary='#ffbd6b';d.palette.secondary='#f1755d';
      text('Рубрика','НАША СЛЕДУЮЩАЯ ЦЕЛЬ',24,12,680,25,14,{letterSpacing:3,fill:'@primary'});text('Название цели','{{title}}',24,48,570,40,28);
      text('Крупная сумма','{{current}}',20,96,480,88,78,{fontWeight:800,letterSpacing:-3});text('Валюта','{{currency}}',498,146,210,35,22,{fill:'#adb3c0'});
      bar('Акцентная линия',24,201,712,5,{radius:0});text('Осталось','Осталось {{remaining}} {{currency}}',24,214,560,24,16,{fill:'#adb3c0'});text('Процент','{{percent}}%',600,214,136,24,16,{textAlign:'right',fill:'@primary'});
    } else if(preset.id==='card') {
      d.width=620;d.height=260;d.palette.primary='#96aaff';d.palette.secondary='#7066ef';d.palette.track='#303a54';
      node('shape','Фон карточки',10,10,600,240,{fill:'@surface',radius:24,stroke:'#34415f',strokeWidth:1});
      text('Название цели','{{title}}',36,32,548,38,28);text('Собрано','{{current}} {{currency}}',36,88,360,48,38);text('Процент','{{percent}}%',420,94,164,40,30,{fill:'@primary',textAlign:'right'});
      bar('Прогресс',36,151,548,14,{radius:7});text('До цели','Цель: {{goal}} {{currency}}',36,179,548,26,18,{fill:'#9ca9c5',fontWeight:400});text('Последний донат','{{lastName}}  {{lastAmount}}',36,214,548,22,14,{fill:'#9ca9c5',fontWeight:400});
    } else if(preset.id==='ring') {
      d.width=620;d.height=280;d.palette.primary='#6be2d2';d.palette.secondary='#69a7ef';d.palette.track='#263a47';
      bar('Кольцевой прогресс',20,20,240,240,{gradient:false},{shape:'ring',thickness:16});text('Процент в центре','{{percent}}%',45,107,190,62,44,{textAlign:'center'});
      text('Название цели','{{title}}',290,55,304,72,28);text('Собрано','{{current}} {{currency}}',290,143,304,40,30,{fill:'@primary'});text('Цель','из {{goal}} {{currency}}',290,192,304,30,19,{fill:'#a2b4bf',fontWeight:400});
    } else if(preset.id==='steps') {
      d.height=200;d.palette.primary='#ffd66f';d.palette.secondary='#ee9771';d.palette.track='#4a403b';
      text('Название цели','{{title}}',24,16,560,42,30);text('Процент','{{percent}}%',594,20,142,36,26,{fill:'@primary',textAlign:'right'});
      bar('Сегменты',24,80,712,38,{radius:5,gradient:false},{shape:'segments',segments:12,gap:8});
      text('Начало','0',24,132,100,24,16,{fill:'#b5aaa0'});text('Середина','ПОЛОВИНА ПУТИ',250,132,260,24,13,{textAlign:'center',fill:'#b5aaa0',letterSpacing:1});text('Цель','{{goal}} {{currency}}',536,132,200,24,16,{textAlign:'right'});text('Собрано','Уже собрано {{current}} {{currency}}',24,166,712,26,18,{fontWeight:400});
    } else if(preset.id==='vertical') {
      d.width=300;d.height=560;d.palette.primary='#ec9bce';d.palette.secondary='#a78aed';d.palette.track='#383048';
      text('Название цели','{{title}}',20,16,260,76,28,{textAlign:'center'});bar('Вертикальная шкала',100,114,100,320,{radius:24,gradientAngle:0},{direction:'up'});
      text('Процент','{{percent}}%',105,250,90,50,28,{textAlign:'center'});text('Собрано','{{current}} {{currency}}',20,459,260,38,28,{textAlign:'center'});text('Цель','из {{goal}} {{currency}}',20,508,260,28,18,{textAlign:'center',fill:'#bbaacb',fontWeight:400});
    } else {
      d.width=500;d.height=460;d.palette.primary='#ff877e';d.palette.secondary='#f0b672';d.palette.track='#49343e';
      node('shape','Внешний медальон',124,36,252,252,{fill:'@surface',radius:44,stroke:'@primary',strokeWidth:2},{rotation:45});
      bar('Заполнение фигуры',150,62,200,200,{radius:36,gradientAngle:0},{direction:'up'}).rotation=45;
      text('Процент','{{percent}}%',150,133,200,62,44,{textAlign:'center',shadowColor:'#172136',shadowBlur:8});text('Название цели','{{title}}',24,320,452,48,30,{textAlign:'center'});text('Сумма и цель','{{current}} / {{goal}} {{currency}}',24,386,452,36,24,{textAlign:'center',fill:'@primary'});
    }
    return M.normalize(d);
  }
  global.VDGWidgetPresets={list:()=>presets.map(p=>Object.assign({},p)),create};
})(window);

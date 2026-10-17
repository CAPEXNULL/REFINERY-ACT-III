export const DEFAULT_PROFILE = {
  schema:'refinery-profile/v1', project:'REFINERY', site:'Refinery · Unit 01',
  language:'ru', theme:'light', units:{temperature:'K',pressure:'kPa'},
  wall:{scale:1,dense:false,autoRefresh:true},
  limits:{pressureWarning:145,pressureCritical:155,temperatureWarning:450,temperatureCritical:465,
    pressureDeviation:0.5,sensorDifference:2}, tags:{},
  loops:['feed','separation','condensation','reflux','cooling','protection']
};
export function validateProfile(value){
  if(!value || value.schema!==DEFAULT_PROFILE.schema)throw Error('Unsupported profile schema');
  const p=structuredClone(DEFAULT_PROFILE);
  for(const k of ['project','site']){if(typeof value[k]!=='string'||!value[k].trim()||value[k].length>100||/[\u0000-\u001f]/.test(value[k]))throw Error('Invalid '+k);p[k]=value[k].trim();}
  if(!['ru','en'].includes(value.language)||!['light','dark'].includes(value.theme))throw Error('Invalid language or theme');
  p.language=value.language;p.theme=value.theme;
  if(value.wall!==undefined){
    const w=value.wall;
    if(!w||typeof w.scale!=='number'||!Number.isFinite(w.scale)||w.scale<.8||w.scale>1.6||typeof w.dense!=='boolean'||typeof w.autoRefresh!=='boolean')throw Error('Invalid wall preferences');
    p.wall={scale:w.scale,dense:w.dense,autoRefresh:w.autoRefresh};
  }
  if(!['K','C'].includes(value.units?.temperature)||!['kPa','bar'].includes(value.units?.pressure))throw Error('Invalid units');
  p.units={temperature:value.units.temperature,pressure:value.units.pressure};
  for(const k of Object.keys(p.limits)){
    const v=value.limits?.[k];if(typeof v!=='number'||!Number.isFinite(v)||v<.001||v>2000)throw Error('Invalid limit '+k);p.limits[k]=v;
  }
  if(p.limits.pressureWarning>=p.limits.pressureCritical||p.limits.temperatureWarning>=p.limits.temperatureCritical)throw Error('Warning must be below critical');
  if(p.limits.temperatureWarning<280||p.limits.temperatureCritical>600||p.limits.sensorDifference>50)throw Error('Limits outside model envelope');
  if(!value.tags || typeof value.tags!=='object'||Array.isArray(value.tags)||Object.keys(value.tags).length>200)throw Error('Invalid tag map');
  p.tags={};
  for(const [key,v] of Object.entries(value.tags)){
    if(!/^[A-Za-z0-9:-]{1,64}$/.test(key)||!v||typeof v!=='object')throw Error('Invalid equipment tag');
    const tag={};
    for(const k of ['label','temperature','pressure']){
      if(v[k]!==undefined){if(typeof v[k]!=='string'||v[k].length>100||/[\u0000-\u001f]/.test(v[k]))throw Error('Invalid tag label');tag[k]=v[k];}
    }
    p.tags[key]=tag;
  }
  if(value.loops && JSON.stringify(value.loops)!==JSON.stringify(p.loops))throw Error('Six refinery loop bindings must be retained');
  return p;
}
export const RU={
 overview:'Обзор объекта',signals:'Сигналы',diagnostics:'Диагностика',scenarios:'Сценарии',events:'Тревоги и события',reports:'Отчёты',settings:'Настройка объекта',
 source:'Источник',simulation:'Физическая симуляция',replay:'Архивный расчёт',imported:'Импорт · непроверенный источник',time:'Время просмотра',analysisTime:'Диагноз на',
 equipment:'Оборудование',temperature:'Температура',pressure:'Давление',reference:'Номинальный режим',observation:'Наблюдение',forecast:'Прогноз',
 quality:'Качество данных',simulated:'Расчётные датчики',unverified:'Происхождение не проверено',missing:'Нет данных',normal:'Норма',warning:'Предупреждение',critical:'Критическое',trip:'Защита',
 noResult:'Выберите расчёт из архива или запустите новый сценарий.',run:'Новый расчёт',history:'Архив расчётов',refresh:'Обновить',close:'Закрыть',apply:'Применить',cancel:'Отмена',
 config:'Конфигурация оборудования',fault:'Возмущение симулятора',duration:'Наблюдение, с',severity:'Остаток ресурса',compare:'Рассчитать последствия действий',
 normalMode:'Нормальный режим',cooling_loss:'Потеря охлаждения',heater_loss:'Потеря нагрева',sensor_bias:'Смещение датчика',unknown:'Недостаточно данных',
 queued:'В очереди',initialization:'Подготовка модели',referencePhase:'Номинальная траектория',physical:'Расчёт возмущения',diagnosis:'Диагностика',forecastPhase:'Расчёт действий',feedback:'Проверка и обратная связь',completed:'Расчёт завершён',failed:'Расчёт не принят',interrupted:'Расчёт прерван перезапуском',
 stageProgress:'Выполненные этапы; время завершения не оценивается',processing:'Выполняется расчёт',retry:'Повторить запрос',connection:'Связь с сервисом',ready:'Модель допущена',pending:'Ожидается проверка модели',offline:'Сервис недоступен',previous:'Отображается предыдущий принятый результат',
 material:'Материальные потоки',thermal:'Тепловые воздействия',control:'Сигналы защиты',causal:'Причинная гипотеза',allLoops:'Все шесть контуров',
 feed:'Подача и нагрев',separation:'Ректификация',condensation:'Конденсация',reflux:'Возврат флегмы',cooling:'Охлаждение',protection:'Независимая защита',
 zoomIn:'Увеличить схему',zoomOut:'Уменьшить схему',fit:'Вписать схему',play:'Воспроизвести',pause:'Пауза',snapshot:'Снимок',textSummary:'Текстовая схема',
 rootCause:'Первопричина',modelVersion:'Версия диагностики',confidence:'Достоверность',uncalibrated:'Сходство с шаблоном, не вероятность. Доверительные интервалы не рассчитаны.',
 hypotheses:'Ранжированные гипотезы',evidence:'Наблюдаемые доказательства',feature:'Признак',value:'Значение',similarity:'Сходство',causalAt:'Гипотеза построена по последнему наблюдению',
 selected:'Выбран',hold:'Бездействие',restore_cooling:'Восстановить охлаждение',reduce_heat:'Снизить нагрев',reduce_feed:'Снизить подачу',action:'Действие',product:'Продукт, моль',finalPressure:'Конечное давление',noForecast:'В этом расчёте прогноз действий отсутствует.',conditional:'Условный прогноз при заявленных допущениях; управление оборудованием не выполняется.',
 search:'Поиск по тегу или оборудованию',signal:'Сигнал',tag:'Тег',role:'Назначение',delta:'Отклонение',sort:'Сортировать по значению',allSignals:'Все сигналы',onlyIssues:'Только отклонения',
 alarm:'Тревога',occurred:'Возникла',resolved:'Вернулась в норму',active:'Активна',acknowledged:'Просмотр подтверждён',notAcknowledged:'Не подтверждена',ack:'Подтвердить просмотр',comment:'Комментарий инженера',note:'Добавить заметку',saveNote:'Сохранить заметку',noEvents:'В выбранный момент тревог нет.',ackBoundary:'Подтверждение просмотра не устраняет нарушение. Пороги заданы профилем объекта.',
 noteHint:'Комментарий от 3 до 2000 символов. Локальная запись без удостоверенной личности.',notes:'Журнал инженерных записей',localIdentity:'Локальное рабочее место · личность не удостоверена',
 pressureDeviation:'Отклонение давления от номинала',sensorDifference:'Расхождение основного и независимого датчиков',pressureLimit:'Порог давления',temperatureLimit:'Порог температуры',tripEvent:'Сработала независимая защита',limit:'Порог',
 importResult:'Импорт расчёта',exportJson:'Экспорт JSON',exportCsv:'Экспорт сигналов CSV',print:'Печать отчёта',verification:'Показать истину симулятора после диагностики',sourceHash:'SHA-256 архива',balance:'Контроль балансов',mass:'Компоненты, моль',energy:'Энергия, Дж',
 project:'Название проекта',site:'Объект / участок',language:'Язык',theme:'Оформление',light:'Светлое',dark:'Тёмное',units:'Единицы',thresholds:'Пороги тревог · базовые единицы K / kPa',tags:'Названия оборудования и теги сигналов · JSON',profileImport:'Импорт профиля',profileExport:'Экспорт профиля',profileSaved:'Профиль применён',settingsBoundary:'Профиль меняет отображение и тревоги. Физика и уставки защиты 470 K / 160 kPa от него не меняются.',
 windowStart:'Начало окна, с',windowEnd:'Конец окна, с',resetWindow:'Весь интервал',selectedSignal:'Сигнал графика',open:'Открыть',noHistory:'Принятых расчётов ещё нет.',historyBoundary:'Архив принят сервисом. Импортированные файлы не обучают Персея.',
 simulationBoundary:'Трёхкомпонентная модель участка НПЗ. Промышленная достоверность и вероятности не калиброваны.',profile:'Профиль объекта',resultId:'Идентификатор расчёта',qualification:'Проверка модели',empty:'Нет данных',exported:'Экспорт подготовлен',viewChanged:'Представление обновлено',staleDraft:'Параметры формы относятся к новому запуску; текущий результат сохраняет исходную конфигурацию.',diagramLegend:'Сплошные — физические потоки; пунктир — тепловые и защитные связи; штрих-пунктир — гипотеза.',noActuation:'Только анализ и моделирование',status:'Статус'
};
const EN={overview:'Plant overview',signals:'Signals',diagnostics:'Diagnostics',scenarios:'Scenarios',events:'Alarms & events',reports:'Reports',settings:'Plant settings',
 source:'Source',simulation:'Physics simulation',replay:'Archived calculation',imported:'Imported · unverified source',time:'Inspection time',analysisTime:'Diagnosis at',
 equipment:'Equipment',temperature:'Temperature',pressure:'Pressure',reference:'Nominal reference',observation:'Observation',forecast:'Forecast',quality:'Data quality',simulated:'Simulated sensors',unverified:'Unverified provenance',missing:'Missing data',
 normal:'Normal',warning:'Warning',critical:'Critical',trip:'Protection',noResult:'Open an archived calculation or run a new scenario.',run:'New calculation',history:'Calculation archive',refresh:'Refresh',close:'Close',apply:'Apply',cancel:'Cancel',
 config:'Equipment configuration',fault:'Simulator disturbance',duration:'Observation, s',severity:'Remaining resource',compare:'Calculate action consequences',normalMode:'Normal operation',cooling_loss:'Cooling loss',heater_loss:'Heating loss',sensor_bias:'Sensor bias',unknown:'Insufficient evidence',
 queued:'Queued',initialization:'Model initialization',referencePhase:'Nominal trajectory',physical:'Disturbance calculation',diagnosis:'Diagnosis',forecastPhase:'Action forecasts',feedback:'Verification and feedback',completed:'Calculation completed',failed:'Calculation not accepted',interrupted:'Interrupted by server restart',stageProgress:'Completed phases; completion time is not estimated',processing:'Calculation running',retry:'Retry request',connection:'Service connection',ready:'Model qualified',pending:'Model qualification pending',offline:'Service unavailable',previous:'Showing the previous accepted result',
 material:'Material flows',thermal:'Thermal inputs',control:'Protection signals',causal:'Causal hypothesis',allLoops:'All six loops',feed:'Feed and heating',separation:'Distillation',condensation:'Condensation',reflux:'Reflux return',cooling:'Cooling',protection:'Independent protection',zoomIn:'Zoom in',zoomOut:'Zoom out',fit:'Fit diagram',play:'Play',pause:'Pause',snapshot:'Snapshot',textSummary:'Text topology',
 rootCause:'Root cause',modelVersion:'Diagnostic version',confidence:'Confidence',uncalibrated:'Template similarity, not probability. Confidence intervals are not available.',hypotheses:'Ranked hypotheses',evidence:'Observed evidence',feature:'Feature',value:'Value',similarity:'Similarity',causalAt:'Hypothesis uses the final observation',selected:'Selected',hold:'Hold',restore_cooling:'Restore cooling',reduce_heat:'Reduce heating',reduce_feed:'Reduce feed',action:'Action',product:'Product, mol',finalPressure:'Final pressure',noForecast:'This calculation has no action forecasts.',conditional:'Conditional forecast under stated assumptions; no equipment commands are issued.',
 search:'Search tag or equipment',signal:'Signal',tag:'Tag',role:'Role',delta:'Deviation',sort:'Sort by value',allSignals:'All signals',onlyIssues:'Deviations only',alarm:'Alarm',occurred:'Occurred',resolved:'Returned to normal',active:'Active',acknowledged:'Review acknowledged',notAcknowledged:'Not acknowledged',ack:'Acknowledge review',comment:'Engineering comment',note:'Add note',saveNote:'Save note',noEvents:'No alarms at the selected time.',ackBoundary:'Acknowledgement does not clear the physical condition. Limits come from the plant profile.',noteHint:'3 to 2000 characters. Local record without verified identity.',notes:'Engineering journal',localIdentity:'Local workstation · identity not authenticated',pressureDeviation:'Pressure deviation from nominal',sensorDifference:'Primary and independent sensor disagreement',pressureLimit:'Pressure threshold',temperatureLimit:'Temperature threshold',tripEvent:'Independent protection trip',limit:'Threshold',
 importResult:'Import calculation',exportJson:'Export JSON',exportCsv:'Export signal CSV',print:'Print report',verification:'Reveal simulator truth after diagnosis',sourceHash:'Archive SHA-256',balance:'Conservation evidence',mass:'Components, mol',energy:'Energy, J',project:'Project name',site:'Plant / unit',language:'Language',theme:'Theme',light:'Light',dark:'Dark',units:'Units',thresholds:'Alarm thresholds · base units K / kPa',tags:'Equipment labels and signal tags · JSON',profileImport:'Import profile',profileExport:'Export profile',profileSaved:'Profile applied',settingsBoundary:'Profile controls display and alarms. It does not change physics or protection limits of 470 K / 160 kPa.',
 windowStart:'Window start, s',windowEnd:'Window end, s',resetWindow:'Full interval',selectedSignal:'Chart signal',open:'Open',noHistory:'No accepted calculations yet.',historyBoundary:'Archive contains server-accepted calculations. Imported files do not train Perseus.',simulationBoundary:'Ternary refinery surrogate. Industrial accuracy and probabilities are not calibrated.',profile:'Plant profile',resultId:'Calculation identifier',qualification:'Model qualification',empty:'No data',exported:'Export prepared',viewChanged:'View updated',staleDraft:'Form parameters apply to a new run; the displayed result retains its original configuration.',diagramLegend:'Solid: physical flow; dashed: thermal/protection links; dash-dot: hypothesis.',noActuation:'Analysis and simulation only',status:'Status'};
Object.assign(RU,{heater:'Нагреватель',column:'Ступень колонны',reboiler:'Кипятильник',condenser:'Конденсатор',vapor:'Пар',liquid:'Жидкость',
 wall:'Видеостена',expandAll:'Развернуть всё',collapseAll:'Вернуться к обзору',fullscreen:'Полноэкранный показ',exitFullscreen:'Выйти из полного экрана',
 autoRefresh:'Обновлять последние принятые данные',wallScale:'Размер подписей',dense:'Компактная компоновка',wallBoundary:'Все показатели текущего объекта · принятый расчёт, не поток с реального оборудования',
 histTemperature:'Температуры всего оборудования',histPressure:'Давления всего оборудования',states:'Состояния оборудования',eventTimeline:'Лента обнаруженных событий',
 referenceMarker:'Отметка — номинальное значение',lastAccepted:'Последние принятые данные',clock:'Часы рабочего места',allParameters:'Все параметры',detected:'Обнаружено по датчикам',
 observedLoop:'Сводка по наблюдаемым параметрам',fullscreenUnavailable:'Полный экран недоступен в этой среде. Все показатели остаются видимыми в режиме видеостены.',refreshPaused:'Обновление архива приостановлено',
 tagLabel:'Название оборудования',temperatureTag:'Тег температуры',pressureTag:'Тег давления',advancedConfig:'Расширенная конфигурация JSON',
 skip:'Перейти к содержимому',menu:'Разделы рабочего пространства',legacyTools:'Расчёт рабочих режимов',workspace:'ИНЖЕНЕРНОЕ РАБОЧЕЕ МЕСТО',intelligence:'АНАЛИЗ ТЕХНОЛОГИЧЕСКОГО ПРОЦЕССА',
 stageCount:'ступеней',condenserCount:'конденсаторов',invalidWindow:'Начало окна должно предшествовать окончанию',
 assumedComposition:'Состав смеси в оценке запасов принят номинальным.',assumedSeverity:'Предположен продолжающийся отказ с остатком ресурса 0,5.',
 restorationCondition:'Восстановление охлаждения применимо только при возможности вернуть ресурс.',
 proofFlow:'Наблюдения → Pers_A → DSO → MATAN → сохранённый диагноз → проверка исхода',invalidProfile:'Некорректный профиль: проверьте единицы, пороги и JSON тегов.',invalidImport:'Файл не соответствует схеме расчёта или профиля.',fileTooLarge:'Файл превышает 5 МБ'});
Object.assign(EN,{heater:'Heater',column:'Column stage',reboiler:'Reboiler',condenser:'Condenser',vapor:'Vapor',liquid:'Liquid',skip:'Skip to workspace',menu:'Workspace sections',legacyTools:'Operating point tools',workspace:'ENGINEERING WORKSPACE',intelligence:'PROCESS INTELLIGENCE',
 wall:'Video wall',expandAll:'Expand all',collapseAll:'Return to overview',fullscreen:'Fullscreen presentation',exitFullscreen:'Exit fullscreen',autoRefresh:'Refresh latest accepted data',wallScale:'Label size',dense:'Compact layout',
 wallBoundary:'All current plant parameters · accepted calculation, not a real equipment stream',histTemperature:'All equipment temperatures',histPressure:'All equipment pressures',states:'Equipment states',eventTimeline:'Detected event timeline',
 referenceMarker:'Marker: nominal value',lastAccepted:'Latest accepted data',clock:'Workstation clock',allParameters:'All parameters',detected:'Detected in observations',observedLoop:'Observed parameter summary',
 fullscreenUnavailable:'Fullscreen unavailable in this environment. All parameters remain visible in video-wall view.',refreshPaused:'Archive refresh paused',
 tagLabel:'Equipment label',temperatureTag:'Temperature tag',pressureTag:'Pressure tag',advancedConfig:'Advanced JSON configuration',
 stageCount:'stages',condenserCount:'condensers',invalidWindow:'Window start must precede end',assumedComposition:'Nominal composition is assumed in the inventory estimate.',assumedSeverity:'An ongoing diagnosed fault with resource availability 0.5 is assumed.',restorationCondition:'Cooling restoration is feasible only if the resource can be restored.',
 proofFlow:'Observations → Pers_A → DSO → MATAN → persisted diagnosis → outcome verification',invalidProfile:'Invalid profile: check units, thresholds and tag JSON.',invalidImport:'File does not match the calculation or profile schema.',fileTooLarge:'File exceeds 5 MB'});
export function translate(key,language='ru'){return (language==='en'?EN:RU)[key]||key;}
export function loadProfile(){try{return validateProfile(JSON.parse(localStorage.getItem('refinery-profile-v1')));}catch{return structuredClone(DEFAULT_PROFILE);}}
export function saveProfile(p){localStorage.setItem('refinery-profile-v1',JSON.stringify(validateProfile(p)));}

/** Independent preferences: language never selects a market or storage location. */
export const voiceLocales=['zh-CN','en-US','en-GB','ja-JP','ko-KR','es-ES','pt-PT','de-DE','fr-FR','it-IT'] as const;
export type VoiceLocale=typeof voiceLocales[number];
export type RegionalPreferences={locale:VoiceLocale;market_region:'US'|'EEA'|'UK'|'JP'|'KR';distance_unit:'yd'|'m';temperature_unit:'C'|'F';wind_unit:'m/s'|'mph'|'km/h';timezone:string;data_region:null|'US'|'EEA'|'UK'|'JP'|'KR'};
export const speechHints:Record<VoiceLocale,string[]>={
 'zh-CN':['七号铁','这洞打完了','六杆','两推','一罚','确认','先不记'],
 'en-US':['seven iron','carry','two putts','no penalties','out of bounds'],
 'en-GB':['seven iron','carry','two putts','no penalties','out of bounds'],
 'ja-JP':['7番アイアン','キャリー','2パット','ペナルティなし','OB'],
 'ko-KR':['7번 아이언','캐리','2퍼트','벌타 없음','OB'],
 'es-ES':['hierro 7', 'dos putts', 'sin penalizaciones'],
 'pt-PT':['ferro 7', 'dois putts', 'sem penalizações'],
 'de-DE':['7er-Eisen', 'zwei Putts', 'keine Strafschläge'],
 'fr-FR':['fer 7', 'deux putts', 'sans pénalité'],
 'it-IT':['ferro 7', 'due putt', 'nessuna penalità'],
};
export function voiceLocale(value:string):VoiceLocale {
 if(!(voiceLocales as readonly string[]).includes(value))throw Error('Unsupported voice locale');
 return value as VoiceLocale;
}

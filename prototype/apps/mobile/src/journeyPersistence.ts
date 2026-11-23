/** Account-scoped durable receipts. One document write keeps pending+snapshot atomic. */
export interface LocalStore { getItem(key:string):Promise<string|null>;setItem(key:string,value:string):Promise<void>;removeItem?(key:string):Promise<void>; }
export type SavedJourney={schema:1;snapshot?:unknown;pending?:unknown};
export class JourneyPersistence {
 constructor(private store:LocalStore,private key:string){}
 async read():Promise<SavedJourney>{const raw=await this.store.getItem(this.key);if(!raw)return {schema:1};const saved=JSON.parse(raw);if(saved.schema!==1)throw Error('本地球局版本不兼容，请保留数据并升级应用。');return saved;}
 async write(saved:SavedJourney){await this.store.setItem(this.key,JSON.stringify(saved));}
}

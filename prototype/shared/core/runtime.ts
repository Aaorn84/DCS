import {STRATEGY_POLICY_VERSION} from './strategyPolicy.ts';
/** Explicitly bundled release allowlist. Never downloads executable code or rewrites a round's version. */
import * as currentRules from './roundEngine.ts';
import * as currentDialogue from './dialogue.ts';
import * as currentStrategy from './strategy.ts';
import * as currentSetup from './offlineSetup.ts';
import * as currentWeb from './webJourney.ts';
import * as oldRules from './releases/1.4.0/roundEngine.ts';
import * as oldDialogue from './releases/1.4.0/dialogue.ts';
import * as oldStrategy from './releases/1.4.0/strategy.ts';
import * as oldSetup from './releases/1.4.0/offlineSetup.ts';
import * as oldWeb from './releases/1.4.0/webJourney.ts';
import {parseStrategyPreference} from './personalStrategy.ts';
import * as v15Rules from './releases/1.5.0/roundEngine.ts';
import * as v15Dialogue from './releases/1.5.0/dialogue.ts';
import * as v15Strategy from './releases/1.5.0/strategy.ts';
import * as v15Setup from './releases/1.5.0/offlineSetup.ts';
import * as v15Web from './releases/1.5.0/webJourney.ts';
import {parseStrategyPreference as v15Preference} from './releases/1.5.0/personalStrategy.ts';
import * as v16Rules from './releases/1.6.0/roundEngine.ts';
import * as v16Dialogue from './releases/1.6.0/dialogue.ts';
import * as v16Strategy from './releases/1.6.0/strategy.ts';
import * as v16Setup from './releases/1.6.0/offlineSetup.ts';
import * as v16Web from './releases/1.6.0/webJourney.ts';
import {parseStrategyPreference as v16Preference} from './releases/1.6.0/personalStrategy.ts';
import {CORE_VERSION,CORE_DATASET} from './protocol.ts';
export const SUPPORTED_CORES=['1.4.0','1.5.0','1.6.0',CORE_VERSION] as const;
const releases={
 '1.6.0':{strategy_policy_version:1,version:'1.6.0',dataset:'shared-core-4',personal_strategy:true,parsePreference:v16Preference,...v16Rules,...v16Dialogue,...v16Strategy,...v16Setup,...v16Web},
 '1.5.0':{strategy_policy_version:1,version:'1.5.0',dataset:'shared-core-4',personal_strategy:true,parsePreference:v15Preference,...v15Rules,...v15Dialogue,...v15Strategy,...v15Setup,...v15Web},
 '1.4.0':{strategy_policy_version:undefined,version:'1.4.0',dataset:'shared-core-4',personal_strategy:false,parsePreference:(_text:string)=>null,...oldRules,...oldDialogue,...oldStrategy,...oldSetup,...oldWeb},
 [CORE_VERSION]:{strategy_policy_version:STRATEGY_POLICY_VERSION,version:CORE_VERSION,dataset:CORE_DATASET,personal_strategy:true,parsePreference:parseStrategyPreference,...currentRules,...currentDialogue,...currentStrategy,...currentSetup,...currentWeb},
};
export function coreFor(version:unknown){
 if(typeof version!=='string'||!Object.hasOwn(releases,version))throw new currentRules.CoreRuleError('shared core version mismatch: 核心版本不匹配，请保留球局并安装支持该版本的应用');
 return releases[version as keyof typeof releases];
}
export function coreForPackage(pack:any){const engine=coreFor(pack?.core_version);if(pack?.dataset!==engine.dataset||pack.local_rules_version!==1||pack.local_command_semantics!==2)throw new currentRules.CoreRuleError('核心版本不匹配：incompatible pinned core package');return engine;}
export const isCoreRuleError=(error:unknown)=>error instanceof currentRules.CoreRuleError||error instanceof oldRules.CoreRuleError||error instanceof v15Rules.CoreRuleError||error instanceof v16Rules.CoreRuleError;
// Read-only presentation also follows the pinned version.
export const roundTotals=(state:any)=>coreFor(state?.core_version).localTotals(state);
export const roundChoices=(state:any)=>coreFor(state?.core_version).localChoices(state);

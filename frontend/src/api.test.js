import {describe,it,expect} from 'vitest';
import {summarize,errorMessage} from './api';
describe('backend-derived dashboard data',()=>{it('counts assessments without counting impact as risk',()=>{expect(summarize([{id:1}],[{risk:'HIGH'},{risk:'MEDIUM'},{risk:'LOW'}])).toEqual({repositories:1,analyses:3,high:1,low:1});});it('starts with truthful zero counts',()=>{expect(summarize([],[]).analyses).toBe(0);});it('renders backend validation details',()=>{expect(errorMessage({response:{data:{detail:[{msg:'Required field'}]}}})).toBe('Required field');});});


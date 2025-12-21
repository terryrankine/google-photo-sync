var ce=t=>{throw TypeError(t)};var le=(t,e,s)=>e.has(t)||ce("Cannot "+s);var n=(t,e,s)=>(le(t,e,"read from private field"),s?s.call(t):e.get(t)),p=(t,e,s)=>e.has(t)?ce("Cannot add the same private member more than once"):e instanceof WeakSet?e.add(t):e.set(t,s),l=(t,e,s,a)=>(le(t,e,"write to private field"),a?a.call(t,s):e.set(t,s),s);var se=(t,e,s,a)=>({set _(r){l(t,e,r,s)},get _(){return n(t,e,a)}});import{c as C,a as M,f as $e,s as Oe}from"../chunks/C4q5ovlp.js";import{i as Fe}from"../chunks/CWee0qPb.js";import{B as qe,a6 as Ce,p as ie,f as A,a as oe,c as h,s as y,ab as P,r as d,t as Ae,g as ae,e as De}from"../chunks/BdO5wgpo.js";import{I as j,s as D}from"../chunks/eBBIYMNf.js";import{s as Se}from"../chunks/xojZPGnA.js";import{e as Ee,d as Ne,f as Te,S as Pe,n as g,m as he,b as _,g as _e,Q as ke,i as de,j as He,o as fe,r as pe,k as Ke,h as ge,p as ye,l as Ie,q as je,c as ze}from"../chunks/CA0udPO_.js";import{p as Be,l as z,s as B}from"../chunks/DjHLztBb.js";import{F as Re}from"../chunks/c4NJwOEM.js";import{C as Ve}from"../chunks/CnFYK6WN.js";import{M as Le}from"../chunks/Dk5Je1YU.js";import{o as Ge,a as Je}from"../chunks/Bh4f05T0.js";import{B as Ue}from"../chunks/C23BKA5w.js";function We(t,e,...s){var a=new Ue(t);qe(()=>{const r=e()??null;a.ensure(r,r&&(o=>r(o,...s)))},Ce)}const Xe=!1,Ye=!0,Qt=Object.freeze(Object.defineProperty({__proto__:null,prerender:Ye,ssr:Xe},Symbol.toStringTag,{value:"Module"}));function me(t){return{onFetch:(e,s)=>{var W,E,X,N,Y;const a=e.options,r=(X=(E=(W=e.fetchOptions)==null?void 0:W.meta)==null?void 0:E.fetchMore)==null?void 0:X.direction,o=((N=e.state.data)==null?void 0:N.pages)||[],i=((Y=e.state.data)==null?void 0:Y.pageParams)||[];let u={pages:[],pageParams:[]},w=0;const S=async()=>{let v=!1;const T=f=>{Object.defineProperty(f,"signal",{enumerable:!0,get:()=>(e.signal.aborted?v=!0:e.signal.addEventListener("abort",()=>{v=!0}),e.signal)})},R=Ee(e.options,e.fetchOptions),Z=async(f,x,$)=>{if(v)return Promise.reject();if(x==null&&f.pages.length)return Promise.resolve(f);const te=(()=>{const G={client:e.client,queryKey:e.queryKey,pageParam:x,direction:$?"backward":"forward",meta:e.options.meta};return T(G),G})(),ne=await R(te),{maxPages:V}=e.options,L=$?Ne:Te;return{pages:L(f.pages,ne,V),pageParams:L(f.pageParams,x,V)}};if(r&&o.length){const f=r==="backward",x=f?Ze:ve,$={pages:o,pageParams:i},ee=x(a,$);u=await Z($,ee,f)}else{const f=t??o.length;do{const x=w===0?i[0]??a.initialPageParam:ve(a,u);if(w>0&&x==null)break;u=await Z(u,x),w++}while(w<f)}return u};e.options.persister?e.fetchFn=()=>{var v,T;return(T=(v=e.options).persister)==null?void 0:T.call(v,S,{client:e.client,queryKey:e.queryKey,meta:e.options.meta,signal:e.signal},s)}:e.fetchFn=S}}}function ve(t,{pages:e,pageParams:s}){const a=e.length-1;return e.length>0?t.getNextPageParam(e[a],e,s[a],s):void 0}function Ze(t,{pages:e,pageParams:s}){var a;return e.length>0?(a=t.getPreviousPageParam)==null?void 0:a.call(t,e[0],e,s[0],s):void 0}var Q,m,U,xe,et=(xe=class extends Pe{constructor(e={}){super();p(this,Q);p(this,m);p(this,U);this.config=e,l(this,Q,new Set),l(this,m,new Map),l(this,U,0)}build(e,s,a){const r=new Le({client:e,mutationCache:this,mutationId:++se(this,U)._,options:e.defaultMutationOptions(s),state:a});return this.add(r),r}add(e){n(this,Q).add(e);const s=re(e);if(typeof s=="string"){const a=n(this,m).get(s);a?a.push(e):n(this,m).set(s,[e])}this.notify({type:"added",mutation:e})}remove(e){if(n(this,Q).delete(e)){const s=re(e);if(typeof s=="string"){const a=n(this,m).get(s);if(a)if(a.length>1){const r=a.indexOf(e);r!==-1&&a.splice(r,1)}else a[0]===e&&n(this,m).delete(s)}}this.notify({type:"removed",mutation:e})}canRun(e){const s=re(e);if(typeof s=="string"){const a=n(this,m).get(s),r=a==null?void 0:a.find(o=>o.state.status==="pending");return!r||r===e}else return!0}runNext(e){var a;const s=re(e);if(typeof s=="string"){const r=(a=n(this,m).get(s))==null?void 0:a.find(o=>o!==e&&o.state.isPaused);return(r==null?void 0:r.continue())??Promise.resolve()}else return Promise.resolve()}clear(){g.batch(()=>{n(this,Q).forEach(e=>{this.notify({type:"removed",mutation:e})}),n(this,Q).clear(),n(this,m).clear()})}getAll(){return Array.from(n(this,Q))}find(e){const s={exact:!0,...e};return this.getAll().find(a=>he(s,a))}findAll(e={}){return this.getAll().filter(s=>he(e,s))}notify(e){g.batch(()=>{this.listeners.forEach(s=>{s(e)})})}resumePausedMutations(){const e=this.getAll().filter(s=>s.state.isPaused);return g.batch(()=>Promise.all(e.map(s=>s.continue().catch(_))))}},Q=new WeakMap,m=new WeakMap,U=new WeakMap,xe);function re(t){var e;return(e=t.options.scope)==null?void 0:e.id}var b,be,tt=(be=class extends Pe{constructor(e={}){super();p(this,b);this.config=e,l(this,b,new Map)}build(e,s,a){const r=s.queryKey,o=s.queryHash??_e(r,s);let i=this.get(o);return i||(i=new ke({client:e,queryKey:r,queryHash:o,options:e.defaultQueryOptions(s),state:a,defaultOptions:e.getQueryDefaults(r)}),this.add(i)),i}add(e){n(this,b).has(e.queryHash)||(n(this,b).set(e.queryHash,e),this.notify({type:"added",query:e}))}remove(e){const s=n(this,b).get(e.queryHash);s&&(e.destroy(),s===e&&n(this,b).delete(e.queryHash),this.notify({type:"removed",query:e}))}clear(){g.batch(()=>{this.getAll().forEach(e=>{this.remove(e)})})}get(e){return n(this,b).get(e)}getAll(){return[...n(this,b).values()]}find(e){const s={exact:!0,...e};return this.getAll().find(a=>de(s,a))}findAll(e={}){const s=this.getAll();return Object.keys(e).length>0?s.filter(a=>de(e,a)):s}notify(e){g.batch(()=>{this.listeners.forEach(s=>{s(e)})})}onFocus(){g.batch(()=>{this.getAll().forEach(e=>{e.onFocus()})})}onOnline(){g.batch(()=>{this.getAll().forEach(e=>{e.onOnline()})})}},b=new WeakMap,be),c,O,F,k,H,q,K,I,we,Qe=(we=class{constructor(t={}){p(this,c);p(this,O);p(this,F);p(this,k);p(this,H);p(this,q);p(this,K);p(this,I);l(this,c,t.queryCache||new tt),l(this,O,t.mutationCache||new et),l(this,F,t.defaultOptions||{}),l(this,k,new Map),l(this,H,new Map),l(this,q,0)}mount(){se(this,q)._++,n(this,q)===1&&(l(this,K,He.subscribe(async t=>{t&&(await this.resumePausedMutations(),n(this,c).onFocus())})),l(this,I,fe.subscribe(async t=>{t&&(await this.resumePausedMutations(),n(this,c).onOnline())})))}unmount(){var t,e;se(this,q)._--,n(this,q)===0&&((t=n(this,K))==null||t.call(this),l(this,K,void 0),(e=n(this,I))==null||e.call(this),l(this,I,void 0))}isFetching(t){return n(this,c).findAll({...t,fetchStatus:"fetching"}).length}isMutating(t){return n(this,O).findAll({...t,status:"pending"}).length}getQueryData(t){var s;const e=this.defaultQueryOptions({queryKey:t});return(s=n(this,c).get(e.queryHash))==null?void 0:s.state.data}ensureQueryData(t){const e=this.defaultQueryOptions(t),s=n(this,c).build(this,e),a=s.state.data;return a===void 0?this.fetchQuery(t):(t.revalidateIfStale&&s.isStaleByTime(pe(e.staleTime,s))&&this.prefetchQuery(e),Promise.resolve(a))}getQueriesData(t){return n(this,c).findAll(t).map(({queryKey:e,state:s})=>{const a=s.data;return[e,a]})}setQueryData(t,e,s){const a=this.defaultQueryOptions({queryKey:t}),r=n(this,c).get(a.queryHash),o=r==null?void 0:r.state.data,i=Ke(e,o);if(i!==void 0)return n(this,c).build(this,a).setData(i,{...s,manual:!0})}setQueriesData(t,e,s){return g.batch(()=>n(this,c).findAll(t).map(({queryKey:a})=>[a,this.setQueryData(a,e,s)]))}getQueryState(t){var s;const e=this.defaultQueryOptions({queryKey:t});return(s=n(this,c).get(e.queryHash))==null?void 0:s.state}removeQueries(t){const e=n(this,c);g.batch(()=>{e.findAll(t).forEach(s=>{e.remove(s)})})}resetQueries(t,e){const s=n(this,c);return g.batch(()=>(s.findAll(t).forEach(a=>{a.reset()}),this.refetchQueries({type:"active",...t},e)))}cancelQueries(t,e={}){const s={revert:!0,...e},a=g.batch(()=>n(this,c).findAll(t).map(r=>r.cancel(s)));return Promise.all(a).then(_).catch(_)}invalidateQueries(t,e={}){return g.batch(()=>(n(this,c).findAll(t).forEach(s=>{s.invalidate()}),(t==null?void 0:t.refetchType)==="none"?Promise.resolve():this.refetchQueries({...t,type:(t==null?void 0:t.refetchType)??(t==null?void 0:t.type)??"active"},e)))}refetchQueries(t,e={}){const s={...e,cancelRefetch:e.cancelRefetch??!0},a=g.batch(()=>n(this,c).findAll(t).filter(r=>!r.isDisabled()&&!r.isStatic()).map(r=>{let o=r.fetch(void 0,s);return s.throwOnError||(o=o.catch(_)),r.state.fetchStatus==="paused"?Promise.resolve():o}));return Promise.all(a).then(_)}fetchQuery(t){const e=this.defaultQueryOptions(t);e.retry===void 0&&(e.retry=!1);const s=n(this,c).build(this,e);return s.isStaleByTime(pe(e.staleTime,s))?s.fetch(e):Promise.resolve(s.state.data)}prefetchQuery(t){return this.fetchQuery(t).then(_).catch(_)}fetchInfiniteQuery(t){return t.behavior=me(t.pages),this.fetchQuery(t)}prefetchInfiniteQuery(t){return this.fetchInfiniteQuery(t).then(_).catch(_)}ensureInfiniteQueryData(t){return t.behavior=me(t.pages),this.ensureQueryData(t)}resumePausedMutations(){return fe.isOnline()?n(this,O).resumePausedMutations():Promise.resolve()}getQueryCache(){return n(this,c)}getMutationCache(){return n(this,O)}getDefaultOptions(){return n(this,F)}setDefaultOptions(t){l(this,F,t)}setQueryDefaults(t,e){n(this,k).set(ge(t),{queryKey:t,defaultOptions:e})}getQueryDefaults(t){const e=[...n(this,k).values()],s={};return e.forEach(a=>{ye(t,a.queryKey)&&Object.assign(s,a.defaultOptions)}),s}setMutationDefaults(t,e){n(this,H).set(ge(t),{mutationKey:t,defaultOptions:e})}getMutationDefaults(t){const e=[...n(this,H).values()],s={};return e.forEach(a=>{ye(t,a.mutationKey)&&Object.assign(s,a.defaultOptions)}),s}defaultQueryOptions(t){if(t._defaulted)return t;const e={...n(this,F).queries,...this.getQueryDefaults(t.queryKey),...t,_defaulted:!0};return e.queryHash||(e.queryHash=_e(e.queryKey,e)),e.refetchOnReconnect===void 0&&(e.refetchOnReconnect=e.networkMode!=="always"),e.throwOnError===void 0&&(e.throwOnError=!!e.suspense),!e.networkMode&&e.persister&&(e.networkMode="offlineFirst"),e.queryFn===Ie&&(e.enabled=!1),e}defaultMutationOptions(t){return t!=null&&t._defaulted?t:{...n(this,F).mutations,...(t==null?void 0:t.mutationKey)&&this.getMutationDefaults(t.mutationKey),...t,_defaulted:!0}}clear(){n(this,c).clear(),n(this,O).clear()}},c=new WeakMap,O=new WeakMap,F=new WeakMap,k=new WeakMap,H=new WeakMap,q=new WeakMap,K=new WeakMap,I=new WeakMap,we);function st(t,e){ie(e,!0);const s=Be(e,"client",19,()=>new Qe);Ge(()=>{s().mount()}),je(s()),Je(()=>{s().unmount()});var a=C(),r=A(a);We(r,()=>e.children),M(t,a),oe()}function at(t,e){const s=z(e,["children","$$slots","$$events","$$legacy"]);/**
 * @license lucide-svelte v0.562.0 - ISC
 *
 * ISC License
 *
 * Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2023 as part of Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2025.
 *
 * Permission to use, copy, modify, and/or distribute this software for any
 * purpose with or without fee is hereby granted, provided that the above
 * copyright notice and this permission notice appear in all copies.
 *
 * THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 * WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 * ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 * WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 * ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 * OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 *
 * ---
 *
 * The MIT License (MIT) (for portions derived from Feather)
 *
 * Copyright (c) 2013-2023 Cole Bemis
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 *
 */const a=[["path",{d:"M12 7v14"}],["path",{d:"M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"}]];j(t,B({name:"book-open"},()=>s,{get iconNode(){return a},children:(r,o)=>{var i=C(),u=A(i);D(u,e,"default",{}),M(r,i)},$$slots:{default:!0}}))}function rt(t,e){const s=z(e,["children","$$slots","$$events","$$legacy"]);/**
 * @license lucide-svelte v0.562.0 - ISC
 *
 * ISC License
 *
 * Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2023 as part of Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2025.
 *
 * Permission to use, copy, modify, and/or distribute this software for any
 * purpose with or without fee is hereby granted, provided that the above
 * copyright notice and this permission notice appear in all copies.
 *
 * THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 * WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 * ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 * WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 * ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 * OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 *
 * ---
 *
 * The MIT License (MIT) (for portions derived from Feather)
 *
 * Copyright (c) 2013-2023 Cole Bemis
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 *
 */const a=[["path",{d:"M3 3v16a2 2 0 0 0 2 2h16"}],["path",{d:"M18 17V9"}],["path",{d:"M13 17V5"}],["path",{d:"M8 17v-3"}]];j(t,B({name:"chart-column"},()=>s,{get iconNode(){return a},children:(r,o)=>{var i=C(),u=A(i);D(u,e,"default",{}),M(r,i)},$$slots:{default:!0}}))}function nt(t,e){const s=z(e,["children","$$slots","$$events","$$legacy"]);/**
 * @license lucide-svelte v0.562.0 - ISC
 *
 * ISC License
 *
 * Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2023 as part of Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2025.
 *
 * Permission to use, copy, modify, and/or distribute this software for any
 * purpose with or without fee is hereby granted, provided that the above
 * copyright notice and this permission notice appear in all copies.
 *
 * THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 * WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 * ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 * WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 * ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 * OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 *
 * ---
 *
 * The MIT License (MIT) (for portions derived from Feather)
 *
 * Copyright (c) 2013-2023 Cole Bemis
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 *
 */const a=[["rect",{width:"7",height:"9",x:"3",y:"3",rx:"1"}],["rect",{width:"7",height:"5",x:"14",y:"3",rx:"1"}],["rect",{width:"7",height:"9",x:"14",y:"12",rx:"1"}],["rect",{width:"7",height:"5",x:"3",y:"16",rx:"1"}]];j(t,B({name:"layout-dashboard"},()=>s,{get iconNode(){return a},children:(r,o)=>{var i=C(),u=A(i);D(u,e,"default",{}),M(r,i)},$$slots:{default:!0}}))}function it(t,e){const s=z(e,["children","$$slots","$$events","$$legacy"]);/**
 * @license lucide-svelte v0.562.0 - ISC
 *
 * ISC License
 *
 * Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2023 as part of Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2025.
 *
 * Permission to use, copy, modify, and/or distribute this software for any
 * purpose with or without fee is hereby granted, provided that the above
 * copyright notice and this permission notice appear in all copies.
 *
 * THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 * WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 * ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 * WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 * ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 * OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 *
 * ---
 *
 * The MIT License (MIT) (for portions derived from Feather)
 *
 * Copyright (c) 2013-2023 Cole Bemis
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 *
 */const a=[["path",{d:"M13 5h8"}],["path",{d:"M13 12h8"}],["path",{d:"M13 19h8"}],["path",{d:"m3 17 2 2 4-4"}],["rect",{x:"3",y:"4",width:"6",height:"6",rx:"1"}]];j(t,B({name:"list-todo"},()=>s,{get iconNode(){return a},children:(r,o)=>{var i=C(),u=A(i);D(u,e,"default",{}),M(r,i)},$$slots:{default:!0}}))}function ot(t,e){const s=z(e,["children","$$slots","$$events","$$legacy"]);/**
 * @license lucide-svelte v0.562.0 - ISC
 *
 * ISC License
 *
 * Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2023 as part of Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2025.
 *
 * Permission to use, copy, modify, and/or distribute this software for any
 * purpose with or without fee is hereby granted, provided that the above
 * copyright notice and this permission notice appear in all copies.
 *
 * THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 * WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 * ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 * WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 * ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 * OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 *
 * ---
 *
 * The MIT License (MIT) (for portions derived from Feather)
 *
 * Copyright (c) 2013-2023 Cole Bemis
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 *
 */const a=[["path",{d:"M15 12h-5"}],["path",{d:"M15 8h-5"}],["path",{d:"M19 17V5a2 2 0 0 0-2-2H4"}],["path",{d:"M8 21h12a2 2 0 0 0 2-2v-1a1 1 0 0 0-1-1H11a1 1 0 0 0-1 1v1a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v2a1 1 0 0 0 1 1h3"}]];j(t,B({name:"scroll-text"},()=>s,{get iconNode(){return a},children:(r,o)=>{var i=C(),u=A(i);D(u,e,"default",{}),M(r,i)},$$slots:{default:!0}}))}function ut(t,e){const s=z(e,["children","$$slots","$$events","$$legacy"]);/**
 * @license lucide-svelte v0.562.0 - ISC
 *
 * ISC License
 *
 * Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2023 as part of Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2025.
 *
 * Permission to use, copy, modify, and/or distribute this software for any
 * purpose with or without fee is hereby granted, provided that the above
 * copyright notice and this permission notice appear in all copies.
 *
 * THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 * WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 * ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 * WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 * ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 * OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 *
 * ---
 *
 * The MIT License (MIT) (for portions derived from Feather)
 *
 * Copyright (c) 2013-2023 Cole Bemis
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 *
 */const a=[["path",{d:"M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915"}],["circle",{cx:"12",cy:"12",r:"3"}]];j(t,B({name:"settings"},()=>s,{get iconNode(){return a},children:(r,o)=>{var i=C(),u=A(i);D(u,e,"default",{}),M(r,i)},$$slots:{default:!0}}))}var ct=$e('<nav class="bg-gray-900 border-b border-gray-800 sticky top-0 z-50"><div class="max-w-7xl mx-auto px-4"><div class="flex items-center justify-between h-16"><div class="flex items-center space-x-8"><a href="/" class="text-xl font-bold text-white">GPhoto Sync</a> <div class="flex space-x-1"><a href="/" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><!>Dashboard</a> <a href="/jobs" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><!>Jobs</a> <a href="/stats" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><!>Statistics</a> <a href="/files" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><!>Files</a> <a href="/duplicates" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><!>Duplicates</a> <a href="/logs" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><!>Logs</a> <a href="/config" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><!>Settings</a> <a href="/setup" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><!>Setup</a></div></div> <div class="flex items-center space-x-2"><span></span> <span class="text-gray-400 text-sm capitalize"> </span></div></div></div></nav>');function lt(t,e){ie(e,!0);const s=ze(()=>({queryKey:["status"],queryFn:async()=>{const J=await fetch("/api/status");if(!J.ok)throw new Error("Failed to fetch status");return J.json()},refetchInterval:3e4}));let a=De(()=>{var J;return((J=s.data)==null?void 0:J.status)||"idle"});var r=ct(),o=h(r),i=h(o),u=h(i),w=y(h(u),2),S=h(w),W=h(S);nt(W,{class:"w-4 h-4"}),P(),d(S);var E=y(S,2),X=h(E);it(X,{class:"w-4 h-4"}),P(),d(E);var N=y(E,2),Y=h(N);rt(Y,{class:"w-4 h-4"}),P(),d(N);var v=y(N,2),T=h(v);Re(T,{class:"w-4 h-4"}),P(),d(v);var R=y(v,2),Z=h(R);Ve(Z,{class:"w-4 h-4"}),P(),d(R);var f=y(R,2),x=h(f);ot(x,{class:"w-4 h-4"}),P(),d(f);var $=y(f,2),ee=h($);ut(ee,{class:"w-4 h-4"}),P(),d($);var te=y($,2),ne=h(te);at(ne,{class:"w-4 h-4"}),P(),d(te),d(w),d(u);var V=y(u,2),L=h(V);let G;var ue=y(L,2),Me=h(ue,!0);d(ue),d(V),d(i),d(o),d(r),Ae(()=>{G=Se(L,1,"w-2 h-2 rounded-full",null,G,{"bg-green-500":ae(a)==="idle","bg-blue-500":ae(a)==="running","bg-yellow-500":ae(a)==="paused"}),Oe(Me,ae(a))}),M(t,r),oe()}var ht=$e('<div class="min-h-screen bg-gray-950 text-white"><!> <main class="max-w-7xl mx-auto px-4 py-8"><!></main> <footer class="border-t border-gray-800 mt-12"><div class="max-w-7xl mx-auto px-4 py-6 text-center text-gray-500 text-sm">Google Photos Sync Tool</div></footer></div>');function Mt(t,e){ie(e,!1);const s=new Qe({defaultOptions:{queries:{staleTime:1e3*30,refetchOnWindowFocus:!0}}});Fe(),st(t,{get client(){return s},children:(a,r)=>{var o=ht(),i=h(o);lt(i,{});var u=y(i,2),w=h(u);D(w,e,"default",{}),d(u),P(2),d(o),M(a,o)},$$slots:{default:!0}}),oe()}export{Mt as component,Qt as universal};

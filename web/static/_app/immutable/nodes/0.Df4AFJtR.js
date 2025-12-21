var ue=t=>{throw TypeError(t)};var ce=(t,e,s)=>e.has(t)||ue("Cannot "+s);var n=(t,e,s)=>(ce(t,e,"read from private field"),s?s.call(t):e.get(t)),p=(t,e,s)=>e.has(t)?ue("Cannot add the same private member more than once"):e instanceof WeakSet?e.add(t):e.set(t,s),l=(t,e,s,a)=>(ce(t,e,"write to private field"),a?a.call(t,s):e.set(t,s),s);var ae=(t,e,s,a)=>({set _(r){l(t,e,r,s)},get _(){return n(t,e,a)}});import{c as A,a as _,f as we,s as Qe}from"../chunks/ogBWXyVU.js";import{i as Me}from"../chunks/CdM_fwGK.js";import{A as Oe,a5 as Fe,p as ie,f as C,e as oe,d as h,s as b,aa as M,r as d,t as qe,g as re,k as Ae}from"../chunks/BFd6y1kc.js";import{I as j,s as D,F as Ce}from"../chunks/DNMYGsQS.js";import{s as De}from"../chunks/xAVjXxyA.js";import{e as Se,d as Ee,f as Ne,S as $e,n as g,m as le,b as $,g as Pe,Q as Te,i as he,j as ke,o as de,r as fe,k as He,h as pe,p as ge,l as Ke,q as Ie,c as je}from"../chunks/CSbbpqin.js";import{p as ze,l as z,s as B}from"../chunks/BMtNHPi4.js";import{M as Be}from"../chunks/CXrgShkz.js";import{o as Re,a as Ve}from"../chunks/Dk6I5C0o.js";import{B as Le}from"../chunks/CUvS0D6J.js";function Ge(t,e,...s){var a=new Le(t);Oe(()=>{const r=e()??null;a.ensure(r,r&&(o=>r(o,...s)))},Fe)}const Je=!1,Ue=!0,xt=Object.freeze(Object.defineProperty({__proto__:null,prerender:Ue,ssr:Je},Symbol.toStringTag,{value:"Module"}));function ye(t){return{onFetch:(e,s)=>{var U,E,W,N,X;const a=e.options,r=(W=(E=(U=e.fetchOptions)==null?void 0:U.meta)==null?void 0:E.fetchMore)==null?void 0:W.direction,o=((N=e.state.data)==null?void 0:N.pages)||[],i=((X=e.state.data)==null?void 0:X.pageParams)||[];let u={pages:[],pageParams:[]},w=0;const S=async()=>{let m=!1;const T=f=>{Object.defineProperty(f,"signal",{enumerable:!0,get:()=>(e.signal.aborted?m=!0:e.signal.addEventListener("abort",()=>{m=!0}),e.signal)})},R=Se(e.options,e.fetchOptions),Y=async(f,v,Q)=>{if(m)return Promise.reject();if(v==null&&f.pages.length)return Promise.resolve(f);const ee=(()=>{const se={client:e.client,queryKey:e.queryKey,pageParam:v,direction:Q?"backward":"forward",meta:e.options.meta};return T(se),se})(),te=await R(ee),{maxPages:V}=e.options,L=Q?Ee:Ne;return{pages:L(f.pages,te,V),pageParams:L(f.pageParams,v,V)}};if(r&&o.length){const f=r==="backward",v=f?We:me,Q={pages:o,pageParams:i},Z=v(a,Q);u=await Y(Q,Z,f)}else{const f=t??o.length;do{const v=w===0?i[0]??a.initialPageParam:me(a,u);if(w>0&&v==null)break;u=await Y(u,v),w++}while(w<f)}return u};e.options.persister?e.fetchFn=()=>{var m,T;return(T=(m=e.options).persister)==null?void 0:T.call(m,S,{client:e.client,queryKey:e.queryKey,meta:e.options.meta,signal:e.signal},s)}:e.fetchFn=S}}}function me(t,{pages:e,pageParams:s}){const a=e.length-1;return e.length>0?t.getNextPageParam(e[a],e,s[a],s):void 0}function We(t,{pages:e,pageParams:s}){var a;return e.length>0?(a=t.getPreviousPageParam)==null?void 0:a.call(t,e[0],e,s[0],s):void 0}var P,y,J,ve,Xe=(ve=class extends $e{constructor(e={}){super();p(this,P);p(this,y);p(this,J);this.config=e,l(this,P,new Set),l(this,y,new Map),l(this,J,0)}build(e,s,a){const r=new Be({client:e,mutationCache:this,mutationId:++ae(this,J)._,options:e.defaultMutationOptions(s),state:a});return this.add(r),r}add(e){n(this,P).add(e);const s=ne(e);if(typeof s=="string"){const a=n(this,y).get(s);a?a.push(e):n(this,y).set(s,[e])}this.notify({type:"added",mutation:e})}remove(e){if(n(this,P).delete(e)){const s=ne(e);if(typeof s=="string"){const a=n(this,y).get(s);if(a)if(a.length>1){const r=a.indexOf(e);r!==-1&&a.splice(r,1)}else a[0]===e&&n(this,y).delete(s)}}this.notify({type:"removed",mutation:e})}canRun(e){const s=ne(e);if(typeof s=="string"){const a=n(this,y).get(s),r=a==null?void 0:a.find(o=>o.state.status==="pending");return!r||r===e}else return!0}runNext(e){var a;const s=ne(e);if(typeof s=="string"){const r=(a=n(this,y).get(s))==null?void 0:a.find(o=>o!==e&&o.state.isPaused);return(r==null?void 0:r.continue())??Promise.resolve()}else return Promise.resolve()}clear(){g.batch(()=>{n(this,P).forEach(e=>{this.notify({type:"removed",mutation:e})}),n(this,P).clear(),n(this,y).clear()})}getAll(){return Array.from(n(this,P))}find(e){const s={exact:!0,...e};return this.getAll().find(a=>le(s,a))}findAll(e={}){return this.getAll().filter(s=>le(e,s))}notify(e){g.batch(()=>{this.listeners.forEach(s=>{s(e)})})}resumePausedMutations(){const e=this.getAll().filter(s=>s.state.isPaused);return g.batch(()=>Promise.all(e.map(s=>s.continue().catch($))))}},P=new WeakMap,y=new WeakMap,J=new WeakMap,ve);function ne(t){var e;return(e=t.options.scope)==null?void 0:e.id}var x,be,Ye=(be=class extends $e{constructor(e={}){super();p(this,x);this.config=e,l(this,x,new Map)}build(e,s,a){const r=s.queryKey,o=s.queryHash??Pe(r,s);let i=this.get(o);return i||(i=new Te({client:e,queryKey:r,queryHash:o,options:e.defaultQueryOptions(s),state:a,defaultOptions:e.getQueryDefaults(r)}),this.add(i)),i}add(e){n(this,x).has(e.queryHash)||(n(this,x).set(e.queryHash,e),this.notify({type:"added",query:e}))}remove(e){const s=n(this,x).get(e.queryHash);s&&(e.destroy(),s===e&&n(this,x).delete(e.queryHash),this.notify({type:"removed",query:e}))}clear(){g.batch(()=>{this.getAll().forEach(e=>{this.remove(e)})})}get(e){return n(this,x).get(e)}getAll(){return[...n(this,x).values()]}find(e){const s={exact:!0,...e};return this.getAll().find(a=>he(s,a))}findAll(e={}){const s=this.getAll();return Object.keys(e).length>0?s.filter(a=>he(e,a)):s}notify(e){g.batch(()=>{this.listeners.forEach(s=>{s(e)})})}onFocus(){g.batch(()=>{this.getAll().forEach(e=>{e.onFocus()})})}onOnline(){g.batch(()=>{this.getAll().forEach(e=>{e.onOnline()})})}},x=new WeakMap,be),c,O,F,k,H,q,K,I,xe,_e=(xe=class{constructor(t={}){p(this,c);p(this,O);p(this,F);p(this,k);p(this,H);p(this,q);p(this,K);p(this,I);l(this,c,t.queryCache||new Ye),l(this,O,t.mutationCache||new Xe),l(this,F,t.defaultOptions||{}),l(this,k,new Map),l(this,H,new Map),l(this,q,0)}mount(){ae(this,q)._++,n(this,q)===1&&(l(this,K,ke.subscribe(async t=>{t&&(await this.resumePausedMutations(),n(this,c).onFocus())})),l(this,I,de.subscribe(async t=>{t&&(await this.resumePausedMutations(),n(this,c).onOnline())})))}unmount(){var t,e;ae(this,q)._--,n(this,q)===0&&((t=n(this,K))==null||t.call(this),l(this,K,void 0),(e=n(this,I))==null||e.call(this),l(this,I,void 0))}isFetching(t){return n(this,c).findAll({...t,fetchStatus:"fetching"}).length}isMutating(t){return n(this,O).findAll({...t,status:"pending"}).length}getQueryData(t){var s;const e=this.defaultQueryOptions({queryKey:t});return(s=n(this,c).get(e.queryHash))==null?void 0:s.state.data}ensureQueryData(t){const e=this.defaultQueryOptions(t),s=n(this,c).build(this,e),a=s.state.data;return a===void 0?this.fetchQuery(t):(t.revalidateIfStale&&s.isStaleByTime(fe(e.staleTime,s))&&this.prefetchQuery(e),Promise.resolve(a))}getQueriesData(t){return n(this,c).findAll(t).map(({queryKey:e,state:s})=>{const a=s.data;return[e,a]})}setQueryData(t,e,s){const a=this.defaultQueryOptions({queryKey:t}),r=n(this,c).get(a.queryHash),o=r==null?void 0:r.state.data,i=He(e,o);if(i!==void 0)return n(this,c).build(this,a).setData(i,{...s,manual:!0})}setQueriesData(t,e,s){return g.batch(()=>n(this,c).findAll(t).map(({queryKey:a})=>[a,this.setQueryData(a,e,s)]))}getQueryState(t){var s;const e=this.defaultQueryOptions({queryKey:t});return(s=n(this,c).get(e.queryHash))==null?void 0:s.state}removeQueries(t){const e=n(this,c);g.batch(()=>{e.findAll(t).forEach(s=>{e.remove(s)})})}resetQueries(t,e){const s=n(this,c);return g.batch(()=>(s.findAll(t).forEach(a=>{a.reset()}),this.refetchQueries({type:"active",...t},e)))}cancelQueries(t,e={}){const s={revert:!0,...e},a=g.batch(()=>n(this,c).findAll(t).map(r=>r.cancel(s)));return Promise.all(a).then($).catch($)}invalidateQueries(t,e={}){return g.batch(()=>(n(this,c).findAll(t).forEach(s=>{s.invalidate()}),(t==null?void 0:t.refetchType)==="none"?Promise.resolve():this.refetchQueries({...t,type:(t==null?void 0:t.refetchType)??(t==null?void 0:t.type)??"active"},e)))}refetchQueries(t,e={}){const s={...e,cancelRefetch:e.cancelRefetch??!0},a=g.batch(()=>n(this,c).findAll(t).filter(r=>!r.isDisabled()&&!r.isStatic()).map(r=>{let o=r.fetch(void 0,s);return s.throwOnError||(o=o.catch($)),r.state.fetchStatus==="paused"?Promise.resolve():o}));return Promise.all(a).then($)}fetchQuery(t){const e=this.defaultQueryOptions(t);e.retry===void 0&&(e.retry=!1);const s=n(this,c).build(this,e);return s.isStaleByTime(fe(e.staleTime,s))?s.fetch(e):Promise.resolve(s.state.data)}prefetchQuery(t){return this.fetchQuery(t).then($).catch($)}fetchInfiniteQuery(t){return t.behavior=ye(t.pages),this.fetchQuery(t)}prefetchInfiniteQuery(t){return this.fetchInfiniteQuery(t).then($).catch($)}ensureInfiniteQueryData(t){return t.behavior=ye(t.pages),this.ensureQueryData(t)}resumePausedMutations(){return de.isOnline()?n(this,O).resumePausedMutations():Promise.resolve()}getQueryCache(){return n(this,c)}getMutationCache(){return n(this,O)}getDefaultOptions(){return n(this,F)}setDefaultOptions(t){l(this,F,t)}setQueryDefaults(t,e){n(this,k).set(pe(t),{queryKey:t,defaultOptions:e})}getQueryDefaults(t){const e=[...n(this,k).values()],s={};return e.forEach(a=>{ge(t,a.queryKey)&&Object.assign(s,a.defaultOptions)}),s}setMutationDefaults(t,e){n(this,H).set(pe(t),{mutationKey:t,defaultOptions:e})}getMutationDefaults(t){const e=[...n(this,H).values()],s={};return e.forEach(a=>{ge(t,a.mutationKey)&&Object.assign(s,a.defaultOptions)}),s}defaultQueryOptions(t){if(t._defaulted)return t;const e={...n(this,F).queries,...this.getQueryDefaults(t.queryKey),...t,_defaulted:!0};return e.queryHash||(e.queryHash=Pe(e.queryKey,e)),e.refetchOnReconnect===void 0&&(e.refetchOnReconnect=e.networkMode!=="always"),e.throwOnError===void 0&&(e.throwOnError=!!e.suspense),!e.networkMode&&e.persister&&(e.networkMode="offlineFirst"),e.queryFn===Ke&&(e.enabled=!1),e}defaultMutationOptions(t){return t!=null&&t._defaulted?t:{...n(this,F).mutations,...(t==null?void 0:t.mutationKey)&&this.getMutationDefaults(t.mutationKey),...t,_defaulted:!0}}clear(){n(this,c).clear(),n(this,O).clear()}},c=new WeakMap,O=new WeakMap,F=new WeakMap,k=new WeakMap,H=new WeakMap,q=new WeakMap,K=new WeakMap,I=new WeakMap,xe);function Ze(t,e){ie(e,!0);const s=ze(e,"client",19,()=>new _e);Re(()=>{s().mount()}),Ie(s()),Ve(()=>{s().unmount()});var a=A(),r=C(a);Ge(r,()=>e.children),_(t,a),oe()}function et(t,e){const s=z(e,["children","$$slots","$$events","$$legacy"]);/**
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
 */const a=[["path",{d:"M12 7v14"}],["path",{d:"M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"}]];j(t,B({name:"book-open"},()=>s,{get iconNode(){return a},children:(r,o)=>{var i=A(),u=C(i);D(u,e,"default",{}),_(r,i)},$$slots:{default:!0}}))}function tt(t,e){const s=z(e,["children","$$slots","$$events","$$legacy"]);/**
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
 */const a=[["path",{d:"M3 3v16a2 2 0 0 0 2 2h16"}],["path",{d:"M18 17V9"}],["path",{d:"M13 17V5"}],["path",{d:"M8 17v-3"}]];j(t,B({name:"chart-column"},()=>s,{get iconNode(){return a},children:(r,o)=>{var i=A(),u=C(i);D(u,e,"default",{}),_(r,i)},$$slots:{default:!0}}))}function st(t,e){const s=z(e,["children","$$slots","$$events","$$legacy"]);/**
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
 */const a=[["rect",{width:"7",height:"9",x:"3",y:"3",rx:"1"}],["rect",{width:"7",height:"5",x:"14",y:"3",rx:"1"}],["rect",{width:"7",height:"9",x:"14",y:"12",rx:"1"}],["rect",{width:"7",height:"5",x:"3",y:"16",rx:"1"}]];j(t,B({name:"layout-dashboard"},()=>s,{get iconNode(){return a},children:(r,o)=>{var i=A(),u=C(i);D(u,e,"default",{}),_(r,i)},$$slots:{default:!0}}))}function at(t,e){const s=z(e,["children","$$slots","$$events","$$legacy"]);/**
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
 */const a=[["path",{d:"M13 5h8"}],["path",{d:"M13 12h8"}],["path",{d:"M13 19h8"}],["path",{d:"m3 17 2 2 4-4"}],["rect",{x:"3",y:"4",width:"6",height:"6",rx:"1"}]];j(t,B({name:"list-todo"},()=>s,{get iconNode(){return a},children:(r,o)=>{var i=A(),u=C(i);D(u,e,"default",{}),_(r,i)},$$slots:{default:!0}}))}function rt(t,e){const s=z(e,["children","$$slots","$$events","$$legacy"]);/**
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
 */const a=[["path",{d:"M15 12h-5"}],["path",{d:"M15 8h-5"}],["path",{d:"M19 17V5a2 2 0 0 0-2-2H4"}],["path",{d:"M8 21h12a2 2 0 0 0 2-2v-1a1 1 0 0 0-1-1H11a1 1 0 0 0-1 1v1a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v2a1 1 0 0 0 1 1h3"}]];j(t,B({name:"scroll-text"},()=>s,{get iconNode(){return a},children:(r,o)=>{var i=A(),u=C(i);D(u,e,"default",{}),_(r,i)},$$slots:{default:!0}}))}function nt(t,e){const s=z(e,["children","$$slots","$$events","$$legacy"]);/**
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
 */const a=[["path",{d:"M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915"}],["circle",{cx:"12",cy:"12",r:"3"}]];j(t,B({name:"settings"},()=>s,{get iconNode(){return a},children:(r,o)=>{var i=A(),u=C(i);D(u,e,"default",{}),_(r,i)},$$slots:{default:!0}}))}var it=we('<nav class="bg-gray-900 border-b border-gray-800 sticky top-0 z-50"><div class="max-w-7xl mx-auto px-4"><div class="flex items-center justify-between h-16"><div class="flex items-center space-x-8"><a href="/" class="text-xl font-bold text-white">GPhoto Sync</a> <div class="flex space-x-1"><a href="/" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><!>Dashboard</a> <a href="/jobs" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><!>Jobs</a> <a href="/stats" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><!>Statistics</a> <a href="/files" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><!>Files</a> <a href="/logs" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><!>Logs</a> <a href="/config" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><!>Settings</a> <a href="/setup" class="text-gray-300 hover:text-white hover:bg-gray-800 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5"><!>Setup</a></div></div> <div class="flex items-center space-x-2"><span></span> <span class="text-gray-400 text-sm capitalize"> </span></div></div></div></nav>');function ot(t,e){ie(e,!0);const s=je(()=>({queryKey:["status"],queryFn:async()=>{const G=await fetch("/api/status");if(!G.ok)throw new Error("Failed to fetch status");return G.json()},refetchInterval:3e4}));let a=Ae(()=>{var G;return((G=s.data)==null?void 0:G.status)||"idle"});var r=it(),o=h(r),i=h(o),u=h(i),w=b(h(u),2),S=h(w),U=h(S);st(U,{class:"w-4 h-4"}),M(),d(S);var E=b(S,2),W=h(E);at(W,{class:"w-4 h-4"}),M(),d(E);var N=b(E,2),X=h(N);tt(X,{class:"w-4 h-4"}),M(),d(N);var m=b(N,2),T=h(m);Ce(T,{class:"w-4 h-4"}),M(),d(m);var R=b(m,2),Y=h(R);rt(Y,{class:"w-4 h-4"}),M(),d(R);var f=b(R,2),v=h(f);nt(v,{class:"w-4 h-4"}),M(),d(f);var Q=b(f,2),Z=h(Q);et(Z,{class:"w-4 h-4"}),M(),d(Q),d(w),d(u);var ee=b(u,2),te=h(ee);let V;var L=b(te,2),se=h(L,!0);d(L),d(ee),d(i),d(o),d(r),qe(()=>{V=De(te,1,"w-2 h-2 rounded-full",null,V,{"bg-green-500":re(a)==="idle","bg-blue-500":re(a)==="running","bg-yellow-500":re(a)==="paused"}),Qe(se,re(a))}),_(t,r),oe()}var ut=we('<div class="min-h-screen bg-gray-950 text-white"><!> <main class="max-w-7xl mx-auto px-4 py-8"><!></main> <footer class="border-t border-gray-800 mt-12"><div class="max-w-7xl mx-auto px-4 py-6 text-center text-gray-500 text-sm">Google Photos Sync Tool</div></footer></div>');function wt(t,e){ie(e,!1);const s=new _e({defaultOptions:{queries:{staleTime:1e3*30,refetchOnWindowFocus:!0}}});Me(),Ze(t,{get client(){return s},children:(a,r)=>{var o=ut(),i=h(o);ot(i,{});var u=b(i,2),w=h(u);D(w,e,"default",{}),d(u),M(2),d(o),_(a,o)},$$slots:{default:!0}}),oe()}export{wt as component,xt as universal};

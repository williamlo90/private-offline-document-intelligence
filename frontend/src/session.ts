// A denied response invalidates the entire mounted workspace, including requests
// already in flight. React discards their updates after that workspace unmounts.
export async function sessionFetch(token:string, invalidate:()=>void, path:string, init:RequestInit={}) {
 const response=await fetch(path,{...init,headers:{...init.headers,Authorization:`Bearer ${token}`},cache:'no-store'});
 if([401,403,404].includes(response.status)) {
  invalidate();
  throw new Error('Access changed. Sign in again to reload your authorized workspace.');
 }
 return response;
}

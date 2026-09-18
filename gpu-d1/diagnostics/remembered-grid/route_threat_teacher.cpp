#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>
// Teacher labels only. Every input is a remembered observation, legal mask or
// geometry-only route output. No hidden map, enemy position or route enters net.
extern "C" void threat_labels(int n,const uint8_t* grids,const float* masks,const float* stats,
 const int8_t* first,const uint8_t* candidates,const float* risks,int64_t* labels){
 const int S=5600,W=80,H=70,dx[]={0,1,0,-1,1,1,-1,-1},dy[]={-1,0,1,0,-1,1,1,-1};
 for(int b=0;b<n;b++){
  auto g=grids+b*14*S;auto m=masks+b*19;auto s=stats+b*7;auto f=first+b*S;auto c=candidates+b*S;auto risk=risks+b*S;
  int p=0;for(int v=0;v<S;v++)if(g[5*S+v])p=v;
  auto nb=[&](int v,int a){int x=v%W+dx[a],y=v/W+dy[a];return x<0||x>=W||y<0||y>=H?-1:y*W+x;};
  auto distance=[&](int a,int z){return std::max(std::abs(a%W-z%W),std::abs(a/W-z/W));};
  std::vector<int>bad,awake;
  for(int v=0;v<S;v++)if(g[11*S+v]){if(risk[v]>.15f)bad.push_back(v);if(g[12*S+v]&&g[9*S+v])awake.push_back(v);}
  auto danger=[&](int v){for(int e:bad)if(distance(v,e)<=6)return true;return false;};
  int action=16,goal=-1;
  if(m[18]){labels[b]=S+1+18;continue;}
  // Heal out of combat. REST uses production interrupt and physical-turn cost.
  if(m[17]){labels[b]=S+1+17;continue;}
  if(!awake.empty()){
   int best=-1,hp=100000;
   for(int a=8;a<16;a++)if(m[a]){int q=nb(p,a-8);if(risk[q]<=.15f&&g[6*S+q]<hp){best=a;hp=g[6*S+q];}}
   if(best>=0)action=best;
   else {
    bool flee=false;for(int e:awake)flee|=risk[e]>.15f;
    if(flee){
     auto safety=[&](int v){int d=100;for(int e:awake)if(risk[e]>.15f)d=std::min(d,distance(v,e));return d;};
     int score=safety(p)*100;
     for(int a=0;a<8;a++)if(m[a]){int q=nb(p,a);if(q<0||!g[q])continue;int value=safety(q)*100+(danger(q)?0:10);if(value>score){score=value;action=a;}}
     // If cornered, attacking is preferable to waiting for certain death.
     if(action==16)for(int a=8;a<16;a++)if(m[a]){int q=nb(p,a-8);if(g[6*S+q]<hp){hp=g[6*S+q];action=a;}}
    }
   }
   labels[b]=S+1+action;continue;
  }
  std::vector<int>d(S,-1),step(S,-1),queue{p};d[p]=0;
  for(size_t j=0;j<queue.size();j++){int v=queue[j];for(int a=0;a<8;a++){int q=nb(v,a);if(q<0||!g[q]||d[q]>=0||danger(q)||(v==p&&!m[a]))continue;d[q]=d[v]+1;step[q]=v==p?a:step[v];queue.push_back(q);}}
  for(int v=0;v<S;v++)if(c[v]&&d[v]>0&&g[4*S+v]&&(goal<0||d[v]<d[goal]))goal=v;
  if(goal<0)for(int v=0;v<S;v++)if(c[v]&&d[v]>0&&(goal<0||d[v]<d[goal]))goal=v;
  if(goal>=0){
   // Executor is terrain-only. If its first move differs from the safe teacher
   // route, label an individual move instead of silently changing execution.
   labels[b]=f[goal]==step[goal]?goal:S+1+step[goal];
  }else{
   // Fight a weak adjacent sleeper if it blocks the only remaining route.
   for(int a=8;a<16;a++)if(m[a]){int q=nb(p,a-8);if(risk[q]<=.15f){action=a;break;}}
   labels[b]=S+1+action;
  }
 }
}

#include <cstdint>
#include <vector>
#include <queue>
#include <algorithm>
// Only observed grid and legal action mask enter. No simulator/map-table access.
extern "C" void routes(int n,const uint8_t* grids,const float* masks,int8_t* first,
                       uint8_t* candidates,int64_t* goals,int64_t* actions){
 constexpr int W=80,H=70,S=W*H;
 const int dx[8]={0,1,0,-1,1,1,-1,-1},dy[8]={-1,0,1,0,-1,1,1,-1};
 for(int b=0;b<n;b++){
  const auto g=grids+b*11*S;const auto m=masks+b*19;
  auto f=first+b*S;auto c=candidates+b*S;
  std::fill(f,f+S,int8_t(-1));std::fill(c,c+S,uint8_t(0));
  int p=0;for(int i=0;i<S;i++)if(g[5*S+i])p=i;
  std::vector<int>d(S,-1),q;q.reserve(S);q.push_back(p);d[p]=0;
  auto neighbor=[&](int v,int a){int x=v%W+dx[a],y=v/W+dy[a];return x<0||x>=W||y<0||y>=H?-1:y*W+x;};
  for(size_t j=0;j<q.size();j++){int v=q[j];for(int a=0;a<8;a++){
   int u=neighbor(v,a);if(u<0||!g[u]||d[u]>=0||(v==p&&!m[a]))continue;
   d[u]=d[v]+1;f[u]=v==p?a:f[v];q.push_back(u);
  }}
  std::vector<uint8_t>front(S,0),seen(S,0);
  for(int v:q){if(g[4*S+v]&&v!=p)c[v]=1;
   for(int a=0;a<8;a++){int u=neighbor(v,a);if(u>=0&&!g[u]&&!g[S+u])front[v]=1;}
  }
  // One fixed-coordinate representative per connected frontier region.
  // No route distance is used to construct representatives.
  for(int start=0;start<S;start++)if(front[start]&&!seen[start]){
   std::vector<int>group{start};seen[start]=1;int rep=S;
   for(size_t j=0;j<group.size();j++){int v=group[j];if(v!=p)rep=std::min(rep,v);
    for(int a=0;a<8;a++){int u=neighbor(v,a);if(u>=0&&front[u]&&!seen[u]){seen[u]=1;group.push_back(u);}}
   }if(rep<S)c[rep]=1;
  }
  int best=-1;for(int v=0;v<S;v++)if(c[v]&&g[4*S+v]&&(best<0||d[v]<d[best]))best=v;
  if(best<0)for(int v=0;v<S;v++)if(c[v]&&(best<0||d[v]<d[best]))best=v;
  goals[b]=best;actions[b]=m[18]>0?18:(best>=0?f[best]:16);
 }
}

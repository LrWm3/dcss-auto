// Navigation from exactly the prepared local/coarse observations and action mask.
// No simulator structs, map arrays, coordinates, labels, files, or callbacks.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <queue>
#include <unordered_map>
#include <vector>
static const int dx[8]={0,1,0,-1,1,1,-1,-1},dy[8]={-1,0,1,0,-1,1,1,-1};
struct Memory {
 std::unordered_map<uint64_t,std::array<int,8>> choices;
 std::array<int,256> visits{}; int lastbin=-1;
};
struct Teacher {std::vector<Memory> memory; bool remember; Teacher(int n,bool r):memory(n),remember(r){} };
static int neighbor(int p,int d,int w,int h){int x=p%w+dx[d],y=p/w+dy[d];return x<0||x>=w||y<0||y>=h?-1:y*w+x;}
static uint64_t fingerprint(const float*l,const float*g){
 uint64_t h=1469598103934665603ULL;
 for(int i=0;i<1125;i++){h^=uint64_t(l[i]>.5f);h*=1099511628211ULL;}
 for(int i=0;i<1536;i++){h^=uint64_t(std::lround(g[i]*65535));h*=1099511628211ULL;}return h;
}
static int choose(Teacher&t,int world,const float*l,const float*g,const float*mask){
 if(mask[18]>0)return 18;
 auto&m=t.memory[world];int bin=int(std::max_element(g+5*256,g+6*256)-(g+5*256));
 if(t.remember&&m.lastbin!=bin){m.visits[bin]++;m.lastbin=bin;}
 int dist[225],first[225],queue[225];std::fill(dist,dist+225,-1);std::fill(first,first+225,-1);
 int head=0,tail=1;queue[0]=112;dist[112]=0;
 auto floor=[&](int p){return l[2*225+p]+l[3*225+p]>.5f;};
 while(head<tail){int p=queue[head++];for(int d=0;d<8;d++){
  int q=neighbor(p,d,15,15);if(q<0||!floor(q)||dist[q]>=0||(p==112&&mask[d]==0))continue;
  dist[q]=dist[p]+1;first[q]=p==112?d:first[p];queue[tail++]=q;
 }}
 int stair=-1;for(int j=1;j<tail;j++){int p=queue[j];if(l[4*225+p]>.5f&&(stair<0||dist[p]<dist[stair]))stair=p;}
 // Exact visible/remembered local geometry takes precedence over coarse routing.
 if(stair>=0)return first[stair];
 bool goal=false;for(int p=0;p<256;p++)goal|=g[4*256+p]>.5f;
 float gd[256];std::fill(gd,gd+256,1e6f);
 using Node=std::pair<float,int>;std::priority_queue<Node,std::vector<Node>,std::greater<Node>> pq;
 auto pass=[&](int p){return g[2*256+p]+g[1*256+p] < .99999f || g[1*256+p]<.99999f;};
 // Channel order: unknown, wall, unvisited floor, visited floor, stairs, player.
 auto traversable=[&](int p){return g[1*256+p]<.99999f;};
 for(int p=0;p<256;p++){
  bool target=goal?g[4*256+p]>.5f:false;
  if(!goal&&g[2*256+p]+g[3*256+p]>0){
   target=g[p]>0;
   for(int d=0;d<8;d++){int q=neighbor(p,d,16,16);if(q>=0&&g[q]>0)target=true;}
  }
  if(target){gd[p]=t.remember&&!goal?std::min(10,m.visits[p])*.5f:0.f;pq.push({gd[p],p});}
 }
 while(!pq.empty()){
  auto [cost,p]=pq.top();pq.pop();if(cost!=gd[p])continue;
  for(int d=0;d<8;d++){int q=neighbor(p,d,16,16);if(q<0||!traversable(q))continue;
   float nc=cost+1.f+(g[q]>.9999f?1.f:0.f);if(nc<gd[q]){gd[q]=nc;pq.push({nc,q});}
  }
 }
 // Exact within-bin position is absent. Average guidance over all positions
 // compatible with the observed player bin, rather than reading simulator XY.
 int bx=bin%16,by=bin/16,xlo=(bx*80+15)/16,xhi=((bx+1)*80+15)/16;
 int ylo=(by*70+15)/16,yhi=((by+1)*70+15)/16;
 auto potential=[&](int p){float total=0;int n=0;
  for(int y=ylo;y<yhi;y++)for(int x=xlo;x<xhi;x++){
   int xx=std::clamp(x+p%15-7,0,79),yy=std::clamp(y+p/15-7,0,69);
   total+=std::min(100.f,gd[(yy*16/70)*16+xx*16/80]);n++;
  }return total/n;
 };
 uint64_t key=fingerprint(l,g);std::array<int,8> used{};
 if(t.remember)used=m.choices[key];
 auto penalty=[&](int a){return t.remember?12.f*std::log1p(float(used[a])):0.f;};
 std::array<float,8> scores;scores.fill(1e9f);bool frontier=false;
 // A frontier attempt ends at the first unknown tile; never pathfind through
 // unobserved terrain as though it were known floor.
 for(int j=0;j<tail;j++){int p=queue[j];for(int d=0;d<8;d++){
  int q=neighbor(p,d,15,15);if(q<0||l[q]<.5f)continue;
  int a=p==112?d:first[p];if(a<0||mask[a]==0)continue;frontier=true;
  float score=(goal?20.f:0.1f)*potential(q)+(goal?.3f:1.f)*(dist[p]+1)+penalty(a);
  scores[a]=std::min(scores[a],score);
 }}
 // Backtracking/local crop exit is necessary when no local frontier remains,
 // or when a known remote stair is the objective.
 if(!frontier||goal)for(int j=1;j<tail;j++){
  int p=queue[j];if(p%15!=0&&p%15!=14&&p/15!=0&&p/15!=14)continue;
  int a=first[p];float score=20.f*potential(p)+.3f*dist[p]+penalty(a);
  scores[a]=std::min(scores[a],score);
 }
 int a=-1;float best=1e9f;for(int d=0;d<8;d++)if(mask[d]>0&&scores[d]<best){a=d;best=scores[d];}
 if(a<0){for(int d=0;d<8;d++)if(mask[d]>0&&(a<0||used[d]<used[a]))a=d;}
 if(a<0)return 16;
 if(t.remember)m.choices[key][a]++;
 return a;
}
extern "C" {
void* obs_teacher_new(int n,int remember){return new Teacher(n,remember);}
void obs_teacher_delete(void*p){delete static_cast<Teacher*>(p);}
void obs_teacher_step(void*p,const float*local,const float*global,const float*mask,int64_t*out){
 auto&t=*static_cast<Teacher*>(p);for(int i=0;i<int(t.memory.size());i++)out[i]=choose(t,i,local+i*1125,global+i*1536,mask+i*19);
}
}

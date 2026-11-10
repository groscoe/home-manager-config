// SPDX-License-Identifier: GPL-2.0-only
#include <bpf/libbpf.h>
#include <bpf/bpf.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "events.h"

static volatile sig_atomic_t stop;
static void stopping(int n) { (void)n; stop = 1; }
static void string(const char *s, size_t n) {
    putchar('"');
    for (size_t i=0; i<n && s[i]; i++) {
        unsigned char c=s[i];
        if (c=='"' || c=='\\') { putchar('\\'); putchar(c); }
        else if (c<32 || c>=127) printf("\\u%04x", c);
        else putchar(c);
    }
    putchar('"');
}
static int event(void *ctx, void *data, size_t size) {
    (void)ctx;
    if (size != sizeof(struct camera_event)) return -EINVAL;
    struct camera_event *e=data;
    printf("{\"kind\":\"event\",\"seq\":%llu,\"time_ns\":%llu,\"start_ns\":%llu,\"pid\":%u,\"uid\":%u,\"major\":%u,\"minor\":%u,\"action\":%u,\"known\":%u,\"name\":", e->seq,e->time_ns,e->start_ns,e->pid,e->uid,e->major,e->minor,e->action,e->known);
    string(e->comm,sizeof(e->comm)); puts("}");
    return 0;
}
static int device(int fd, const char *s, int add) {
    unsigned int major,minor; char extra;
    if (sscanf(s,"%u:%u%c",&major,&minor,&extra)!=2) return -1;
    unsigned long long key=((unsigned long long)major<<32)|minor;
    unsigned char value=1;
    return add ? bpf_map_update_elem(fd,&key,&value,BPF_ANY) : bpf_map_delete_elem(fd,&key);
}
int main(int argc, char **argv) {
    if (argc<2 || geteuid()!=0) { fprintf(stderr,"Root and a fixed BPF object are required.\n"); return 2; }
    setvbuf(stdout,NULL,_IOLBF,0);
    signal(SIGTERM,stopping); signal(SIGINT,stopping);
    struct bpf_object *obj=bpf_object__open_file(argv[1],NULL);
    if (libbpf_get_error(obj)) return 3;
    if (bpf_object__load(obj)) { bpf_object__close(obj); return 4; }
    int dev=bpf_object__find_map_fd_by_name(obj,"devices");
    int stats=bpf_object__find_map_fd_by_name(obj,"counters");
    int rbfd=bpf_object__find_map_fd_by_name(obj,"events");
    for (int i=2;i<argc;i++) if (device(dev,argv[i],1)) return 5;
    struct bpf_link *links[8]={0}; int count=0, result=0;
    struct bpf_program *prog;
    bpf_object__for_each_program(prog,obj) {
        if (count==8) { result=6; goto done; }
        links[count]=bpf_program__attach(prog);
        if (libbpf_get_error(links[count])) { links[count]=NULL; result=7; goto done; }
        count++;
    }
    struct ring_buffer *rb=ring_buffer__new(rbfd,event,NULL,NULL);
    if (!rb) { result=8; goto done; }
    puts("{\"kind\":\"ready\"}");
    fcntl(STDIN_FILENO,F_SETFL,fcntl(STDIN_FILENO,F_GETFL)|O_NONBLOCK);
    char input[128]; size_t used=0; time_t heartbeat=0;
    while (!stop) {
        int n=ring_buffer__poll(rb,100);
        if (n<0 && n!=-EINTR) { result=9; break; }
        char c; ssize_t got;
        while ((got=read(STDIN_FILENO,&c,1))==1) {
            if (c=='\n') {
                input[used]=0;
                if (used>2 && (input[0]=='+' || input[0]=='-')) {
                    if (device(dev,input+2,input[0]=='+') && !(input[0]=='-' && errno==ENOENT)) { result=10; stop=1; }
                } else { result=11; stop=1; }
                used=0;
            } else if (used+1<sizeof(input)) input[used++]=c;
            else { result=12; stop=1; break; }
        }
        if (got==0) break; // Parent exited; detach, do not leave tracing behind.
        if (got<0 && errno!=EAGAIN && errno!=EINTR) { result=13; break; }
        time_t now=time(NULL);
        if (now!=heartbeat) {
            unsigned int key=0; unsigned long long lost=0;
            if (bpf_map_lookup_elem(stats,&key,&lost)) { result=14; break; }
            printf("{\"kind\":\"heartbeat\",\"lost\":%llu}\n",lost); heartbeat=now;
        }
    }
    ring_buffer__free(rb);
done:
    for (int i=0;i<count;i++) bpf_link__destroy(links[i]);
    bpf_object__close(obj);
    return result;
}

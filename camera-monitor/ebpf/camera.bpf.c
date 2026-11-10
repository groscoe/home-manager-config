// SPDX-License-Identifier: GPL-2.0-only
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_tracing.h>
#include "events.h"

// CO-RE resolves field offsets against the running kernel's BTF, not these
// deliberately minimal declarations. No frame, path or argument data is read.
struct inode { unsigned short i_mode; unsigned int i_rdev; } __attribute__((preserve_access_index));
struct file { struct inode *f_inode; unsigned int f_flags; } __attribute__((preserve_access_index));
struct task_struct { struct task_struct *group_leader; unsigned long long start_boottime; } __attribute__((preserve_access_index));
struct { __uint(type, BPF_MAP_TYPE_HASH); __uint(max_entries, 512); __type(key, __u64); __type(value, __u8); } devices SEC(".maps");
struct { __uint(type, BPF_MAP_TYPE_HASH); __uint(max_entries, 8192); __type(key, __u64); __type(value, struct camera_event); } opened_files SEC(".maps");
struct { __uint(type, BPF_MAP_TYPE_ARRAY); __uint(max_entries, 2); __type(key, __u32); __type(value, __u64); } counters SEC(".maps");
struct { __uint(type, BPF_MAP_TYPE_RINGBUF); __uint(max_entries, 1 << 20); } events SEC(".maps");

static __always_inline void lost(void) {
    __u32 k = 0; __u64 *n = bpf_map_lookup_elem(&counters, &k);
    if (n) __sync_fetch_and_add(n, 1);
}
static __always_inline int selected(struct file *f, struct camera_event *e) {
    struct inode *i = BPF_CORE_READ(f, f_inode);
    if ((BPF_CORE_READ(i, i_mode) & 0170000) != 0020000) return 0;
    __u32 d = BPF_CORE_READ(i, i_rdev);
    e->major = d >> 20; e->minor = d & ((1 << 20) - 1);
    __u64 key = ((__u64)e->major << 32) | e->minor;
    // Linux's assigned V4L major includes freshly hotplugged video/subdevices.
    return e->major == 81 || bpf_map_lookup_elem(&devices, &key) != 0;
}
static __always_inline void actor(struct camera_event *e) {
    e->pid = bpf_get_current_pid_tgid() >> 32;
    e->uid = (__u32)bpf_get_current_uid_gid();
    bpf_get_current_comm(e->comm, sizeof(e->comm));
    struct task_struct *task = (void *)bpf_get_current_task();
    struct task_struct *leader = BPF_CORE_READ(task, group_leader);
    e->start_ns = BPF_CORE_READ(leader, start_boottime);
}
static __always_inline void emit(struct camera_event *e) {
    __u32 k = 1; __u64 *n = bpf_map_lookup_elem(&counters, &k);
    if (n) e->seq = __sync_fetch_and_add(n, 1) + 1;
    e->time_ns = bpf_ktime_get_boot_ns();
    struct camera_event *out = bpf_ringbuf_reserve(&events, sizeof(*e), 0);
    if (!out) { lost(); return; }
    __builtin_memcpy(out, e, sizeof(*e));
    bpf_ringbuf_submit(out, 0);
}
SEC("fexit/do_dentry_open")
int BPF_PROG(camera_open, struct file *f, struct inode *inode, void *open_fn, int ret) {
    // O_PATH obtains only a path reference, not permission to use the camera.
    if (ret || (BPF_CORE_READ(f, f_flags) & 010000000)) return 0;
    struct camera_event e = {};
    if (!selected(f, &e)) return 0;
    actor(&e); e.action = 1; e.known = 1;
    __u64 key = (__u64)f;
    if (bpf_map_update_elem(&opened_files, &key, &e, BPF_ANY)) lost();
    emit(&e);
    return 0;
}
SEC("fentry/__fput")
int BPF_PROG(camera_release, struct file *f) {
    struct camera_event e = {};
    if (!selected(f, &e)) return 0;
    __u64 key = (__u64)f;
    struct camera_event *original = bpf_map_lookup_elem(&opened_files, &key);
    if (original) { __builtin_memcpy(&e, original, sizeof(e)); e.known = 1; }
    // Unknown releases include handles opened before attachment. They request
    // reconciliation, but must not invent an opener or a successful-open event.
    e.action = 2;
    emit(&e);
    bpf_map_delete_elem(&opened_files, &key);
    return 0;
}
char LICENSE[] SEC("license") = "GPL";

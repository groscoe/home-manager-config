#ifndef CAMERA_EVENTS_H
#define CAMERA_EVENTS_H
struct camera_event {
    unsigned long long seq, time_ns, start_ns;
    unsigned int pid, uid, major, minor, action, known;
    char comm[16];
};
#endif

#include <stdint.h>
#include <stddef.h>

enum { NATIVE, ARMED, ENTER_PENDING, EXTERNAL, RETURN_PENDING };
enum { OK, BAD_LENGTH, BAD_VERSION, BAD_OPCODE, BAD_ARGUMENT, WRONG_SESSION,
       NOT_READY, BUSY, INCOMPLETE, CONFLICT, BAD_CRC, STALE_SEQUENCE,
       UNSUPPORTED, INTERNAL_FAULT };
enum { CAPS=1, MODE, CHUNK, COMMIT, STATUS, ABORT, BRIGHTNESS, OVERLAYS,
       KEEPALIVE, CHUNK_COMMIT };
enum { FRAME_BYTES=225, OVERLAY_MASK=15 };
#define GUARD UINT32_C(0xc0decafe)
#define U8(a) (*(volatile uint8_t *)(uintptr_t)(a))
#define U32(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define CALL(a) ((void (*)(void))(uintptr_t)((a)|1u))()
#define PENDING U8(0x200027b3)
#define ACTIVE U8(0x200027b2)
#define SUSPENDED U8(0x200027ed)

typedef struct {
    volatile uint32_t ms, epoch, rx_epoch, rx_time;
    volatile uint8_t configured, rx_ready, rx_length, in_busy, bus_invalidating;
    uint8_t mode, coverage, committed, intent, overlays, submitted, page, open_overlays;
    uint16_t staged, accepted, queued, displayed, brightness, lease;
    uint32_t token, closed, crc, intent_crc, activity, stage_time, opened;
    uint32_t revision, expanded, queued_revision, displayed_revision, seen_epoch;
    uint32_t fault;
    uint8_t controls[4];
} State;
typedef struct {
    uint8_t frames[2][228];
    uint16_t rgb[226];
    uint8_t rx[64], reply[64];
    union { State core; uint8_t space[240]; } state;
    uint32_t guard;
} Arena;
_Static_assert(sizeof(Arena)==1280 && offsetof(Arena,rgb)==456 &&
               offsetof(Arena,rx)==908 && offsetof(Arena,state)==1036 &&
               offsetof(Arena,guard)==1276, "V4 SRAM layout");
#ifdef V4_TEST
static Arena arena;
static uint8_t mock_pending, mock_active, mock_suspended, mock_validation=1;
#undef PENDING
#undef ACTIVE
#undef SUSPENDED
#define PENDING mock_pending
#define ACTIVE mock_active
#define SUSPENDED mock_suspended
#define VALIDATED mock_validation
static uint32_t mock_usb[0x600/4];
static uint8_t mock_stock[0x3000];
static void test_stock_call(unsigned address);
static volatile uint8_t *mock_byte(uintptr_t address) {
    if(address>=0x40060000 && address<0x40060600)
        return (uint8_t *)mock_usb+(address-0x40060000);
    return mock_stock+(address-0x20000000);
}
#undef U8
#undef U32
#undef CALL
#define U8(a) (*mock_byte(a))
#define U32(a) (mock_usb[((a)-0x40060000)/4])
#define CALL(a) test_stock_call(a)

#else
#define arena (*(Arena *)(uintptr_t)0x20002820)
#define VALIDATED U8(0x2000269e)
#endif
#define state (arena.state.core)
static const uint8_t prefix[5] = {0,0x3a,0x52,0x34,0xe4};

static void copy(uint8_t *dst, const uint8_t *src, unsigned size) {
    for (unsigned i=0;i<size;i++) dst[i]=src[i];
}
static void clear(uint8_t *dst, unsigned size) {
    for (unsigned i=0;i<size;i++) dst[i]=0;
}
static int equal(const uint8_t *a,const uint8_t *b,unsigned size) {
    for (unsigned i=0;i<size;i++) if(a[i]!=b[i]) return 0;
    return 1;
}
static uint16_t get16(const uint8_t *p) {
    return (uint16_t)(p[0]|(unsigned)p[1]<<8);
}
static uint32_t get32(const uint8_t *p) {
    return get16(p)|((uint32_t)get16(p+2)<<16);
}
static void put16(uint8_t *p,uint16_t n) {
    p[0]=(uint8_t)n; p[1]=(uint8_t)(n>>8);
}
static void put32(uint8_t *p,uint32_t n) {
    put16(p,(uint16_t)n); put16(p+2,(uint16_t)(n>>16));
}
static uint32_t checksum(const uint8_t *p) {
    uint32_t crc=~UINT32_C(0);
    for(unsigned i=0;i<FRAME_BYTES;i++) {
        crc^=p[i];
        for(unsigned bit=0;bit<8;bit++)
            crc=(crc>>1)^((0u-(crc&1u))&UINT32_C(0xedb88320));
    }
    return ~crc;
}
static void init_guards(void) {
    arena.frames[0][225]=0xa5;
    arena.frames[1][225]=0x5a;
    arena.rgb[225]=0xa55a;
    arena.guard=GUARD;
}
static int guards_ok(void) {
    return arena.guard==GUARD && arena.frames[0][225]==0xa5 &&
           arena.frames[1][225]==0x5a && arena.rgb[225]==0xa55a &&
           state.committed<=1 && state.mode<=RETURN_PENDING;
}
static void clear_stage(void) {
    state.staged=0; state.coverage=0; state.intent=0;
}
void v4_revoke(void) {
    if(state.token) state.closed=state.token;
    state.token=0;
    state.accepted=0; state.queued=0; state.displayed=0;
    state.displayed_revision=0; state.lease=0; state.overlays=0;
    clear_stage();
    if(state.mode!=NATIVE) state.mode=RETURN_PENDING;
}
static void latch_fault(void) {
    state.fault=1;
    v4_revoke();
}
void v4_tick(void) { state.ms++; }

void v4_supervise(void) {
    if(arena.guard==0 && !state.fault && state.mode==NATIVE && !state.token &&
       !arena.frames[0][225] && !arena.frames[1][225] && !arena.rgb[225])
        init_guards();
    if(!guards_ok()) latch_fault();
    if(state.seen_epoch!=state.epoch || SUSPENDED || !VALIDATED) {
        state.seen_epoch=state.epoch;
        v4_revoke();
        state.closed=0;
    }
    if(state.submitted && !PENDING) {
        if(state.token && ACTIVE==state.page && !SUSPENDED) {
            state.displayed=state.queued;
            state.displayed_revision=state.queued_revision;
        }
        state.submitted=0; state.queued=0;
    }
    if(state.mode==RETURN_PENDING && !PENDING) state.mode=NATIVE;
    uint32_t now=state.ms;
    if((state.mode==ARMED && now-state.opened>=2000) ||
       (state.token && state.lease && now-state.activity>=state.lease))
        v4_revoke();
    if(state.staged && now-state.stage_time>=1000) clear_stage();
}
static void changed(void) {
    if(++state.revision==0) { state.revision=1; state.expanded=0; }
}
static unsigned commit(uint16_t seq,uint32_t crc) {
    unsigned committed=state.committed;
    if(committed>1) { latch_fault(); return INTERNAL_FAULT; }
    if(seq==state.accepted) return crc==state.crc ? OK : CONFLICT;
    if(state.intent && state.intent_crc!=crc) return CONFLICT;
    if(state.staged!=seq || state.coverage!=31) return INCOMPLETE;
    if(state.accepted!=state.displayed) return BUSY;
    if(checksum(arena.frames[committed^1])!=crc) {
        state.intent=0;
        return BAD_CRC;
    }
    state.committed=(uint8_t)(committed^1); state.accepted=seq; state.crc=crc;
    clear_stage();
    changed();
    if(state.mode==ARMED) state.mode=ENTER_PENDING;
    return OK;
}

static unsigned command(const uint8_t *p,unsigned length) {
    if(length!=64) return BAD_LENGTH;
    unsigned op=p[6], arg=p[7];
    if(p[5]!=1 && !(p[5]==0 && op==CAPS)) return BAD_VERSION;
    if(op<CAPS || op>CHUNK_COMMIT) return BAD_OPCODE;
    uint32_t token=get32(p+8);
    uint16_t seq=get16(p+12);
    unsigned end=14;
    if(op==MODE) {
        if(arg>1) return BAD_ARGUMENT;
        if(arg) end=17;
    } else if(op==CHUNK || op==CHUNK_COMMIT) {
        if(arg>=5 || (op==CHUNK_COMMIT && arg!=4)) return BAD_ARGUMENT;
        end=arg==4 ? (op==CHUNK_COMMIT ? 51 : 47) : 62;
    } else if(op==COMMIT) end=18;
    else if(op==BRIGHTNESS) end=16;
    if(op!=MODE && op!=CHUNK && op!=CHUNK_COMMIT && op!=OVERLAYS && arg)
        return BAD_ARGUMENT;
    int has_frame=op==CHUNK || op==CHUNK_COMMIT || op==ABORT || op==COMMIT;
    if((seq!=0)!=has_frame || !get16(p+62) || (op==CAPS && token)) return BAD_ARGUMENT;
    for(unsigned i=end;i<62;i++) if(p[i]) return BAD_ARGUMENT;
    if(op==CAPS || (op==STATUS && !token)) return OK;
    if(op==MODE && !arg) {
        if(token && token==state.token) { v4_revoke(); return OK; }
        return token && !state.token && token==state.closed ? OK : WRONG_SESSION;
    }
    if(state.fault) return INTERNAL_FAULT;
    if(!state.configured || SUSPENDED || !VALIDATED || !arena.guard ||
       state.seen_epoch!=state.epoch) return NOT_READY;
    if(!guards_ok()) { latch_fault(); return INTERNAL_FAULT; }
    if(op==MODE) {
        uint16_t lease=get16(p+14);
        if(!token || (lease && (lease<1000 || lease>60000))) return BAD_ARGUMENT;
        if(p[16]&~OVERLAY_MASK) return UNSUPPORTED;
        if(state.token==token)
            return state.lease==lease && state.open_overlays==p[16] ? OK : CONFLICT;
        if(state.mode!=NATIVE) return BUSY;
        if(token==state.closed) return WRONG_SESSION;
        state.closed=0; state.token=token; state.lease=lease;
        state.overlays=p[16]; state.open_overlays=p[16]; state.brightness=65535;
        state.opened=state.ms; state.mode=ARMED;
        return OK;
    }
    if(!token || token!=state.token) return WRONG_SESSION;
    if(op==STATUS || op==KEEPALIVE) return OK;
    if(op==BRIGHTNESS || op==OVERLAYS) {
        if(op==OVERLAYS && (arg&~OVERLAY_MASK)) return UNSUPPORTED;
        uint16_t brightness=op==BRIGHTNESS ? get16(p+14) : state.brightness;
        unsigned overlays=op==OVERLAYS ? arg : state.overlays;
        if(brightness!=state.brightness || overlays!=state.overlays) {
            state.brightness=brightness; state.overlays=(uint8_t)overlays;
            changed();
        }
        return OK;
    }
    if(seq!=state.accepted && seq!=(uint32_t)state.accepted+1) return STALE_SEQUENCE;
    if(op==ABORT) {
        if(seq==state.accepted) return CONFLICT;
        clear_stage();
        return OK;
    }
    if(op==COMMIT) return commit(seq,get32(p+14));
    unsigned size=arg==4 ? 33 : 48;
    unsigned bit=1u<<arg;
    unsigned committed=state.committed;
    if(committed>1) { latch_fault(); return INTERNAL_FAULT; }
    uint8_t *dst=arena.frames[committed^(seq!=state.accepted)]+48*arg;
    uint32_t crc=op==CHUNK_COMMIT ? get32(p+47) : 0;
    if(seq==state.accepted)
        return equal(dst,p+14,size) && (op!=CHUNK_COMMIT || crc==state.crc) ? OK : CONFLICT;
    if(state.coverage&bit) {
        if(!equal(dst,p+14,size)) return CONFLICT;
    }
    if(op==CHUNK_COMMIT && state.intent && state.intent_crc!=crc) return CONFLICT;
    copy(dst,p+14,size);
    state.staged=seq; state.coverage|=(uint8_t)bit; state.stage_time=state.ms;
    if(op==CHUNK_COMMIT) { state.intent=1; state.intent_crc=crc; }
    return state.intent ? commit(seq,state.intent_crc) : OK;
}

static void respond(const uint8_t *p,unsigned length) {
    uint8_t *r=arena.reply;
    unsigned status=command(p,length);
    uint32_t token=length>=12 ? get32(p+8) : 0;
    if(status==OK && token && token==state.token) state.activity=state.ms;
    clear(r,64); copy(r,prefix,5);
    r[5]=1; r[6]=(length>=7 ? p[6] : 0)|0x80; r[7]=(uint8_t)status;
    if(length>=12) put32(r+8,token);
    if(length>=14) put16(r+12,get16(p+12));
    r[14]=state.mode;
    if(token && token==state.token) {
        r[15]=state.coverage; put16(r+16,state.staged);
        put16(r+18,state.accepted); put16(r+20,state.queued); put16(r+22,state.displayed);
        put32(r+24,state.revision); put32(r+28,state.displayed_revision);
        put16(r+32,state.brightness); r[34]=state.overlays; put16(r+50,state.lease);
    }
    r[35]=OVERLAY_MASK; put32(r+36,31); put32(r+40,0x01160001);
    r[44]=75; r[45]=5; r[46]=15; r[47]=16; r[48]=5; r[49]=64;
    r[52]=state.configured | ((SUSPENDED!=0)<<1) | ((state.submitted && PENDING)<<2);
    if(length>=8) r[53]=p[7];
    if(length>=64) put16(r+62,get16(p+62));
}

static uint16_t scale(uint8_t sample,uint16_t brightness) {
    uint32_t x=(uint32_t)sample*257u*brightness+32767u;
    /* Exact unsigned division by 65535 over this product range. */
    return (uint16_t)((x+1u+(x>>16))>>16);
}
static unsigned remap(unsigned slot) {
    if(slot==63 || slot==64) return 127-slot;
    if(slot==66 || slot==67) return 133-slot;
    return slot;
}

int v4_compose(uintptr_t *frame) {
    if((arena.guard || state.mode!=NATIVE) && !guards_ok()) latch_fault();
    if(state.fault) return PENDING!=0;
    if(state.mode==RETURN_PENDING) return PENDING!=0;
    if(state.mode!=EXTERNAL && state.mode!=ENTER_PENDING) return 0;
    if(PENDING || state.fault || state.seen_epoch!=state.epoch || SUSPENDED) return 1;
    if(state.expanded!=state.revision) {
        unsigned committed=state.committed;
        if(committed>1) { latch_fault(); return 0; }
        const uint8_t *src=arena.frames[committed];
        for(unsigned slot=0;slot<75;slot++) {
            unsigned dst=remap(slot)*3;
            for(unsigned c=0;c<3;c++) arena.rgb[dst+c]=scale(src[slot*3+c],state.brightness);
        }
        state.expanded=state.revision;
    }
    frame[8]=(uintptr_t)arena.rgb;
    if(!(state.overlays&1)) frame[9]&=~(uintptr_t)2;
    if(!(state.overlays&2)) frame[10]=0;
    unsigned count=(unsigned)(uint8_t)frame[18];
    const uint8_t *controls=(const uint8_t *)frame[17];
    clear(state.controls,4);
    for(unsigned i=0;i<count && i<2;i++)
        if(state.overlays&(4u<<i)) copy(state.controls+2*i,controls+2*i,2);
    frame[17]=(uintptr_t)state.controls;
    frame[18]=(state.controls[0] || state.controls[2]) ? (count>2 ? 2 : count) : 0;
    state.page=ACTIVE^1; state.queued=state.accepted;
    state.queued_revision=state.revision; state.submitted=1; state.mode=EXTERNAL;
    return 0;
}

#define USB_INTSTS U32(0x40060004)
#define USB_ATTR U32(0x40060010)
#define USB_FLDET U32(0x40060014)
#define EP_IN U32(0x40060520)
#define EP_OUT U32(0x40060530)
#define IN_LEN U32(0x40060524)
#define OUT_LEN U32(0x40060534)
#define USB_RAM 0x40060100u
#define IN_COMPLETE (1u<<18)
#define STOCK_READY U8(0x2000269f)

#ifdef V4_TEST
static unsigned lock_irq(void) { return 0; }
static void unlock_irq(unsigned flags) { (void)flags; }
#else
static unsigned lock_irq(void) {
    unsigned flags;
    __asm__ volatile("mrs %0, primask\ncpsid i" : "=r"(flags) :: "memory");
    return flags;
}
static void unlock_irq(unsigned flags) {
    if(!(flags&1u)) __asm__ volatile("cpsie i" ::: "memory");
}
#endif

void v4_usb_event(void) {
    uint32_t flags=USB_INTSTS;
    uint32_t bus=(flags&1u) ? USB_ATTR&7u : 0;
    int detach=(flags&4u) && !(USB_FLDET&1u);
    state.bus_invalidating=(bus!=0 || detach);
    if(bus || detach) {
        state.epoch++;
        state.in_busy=0;
        if((bus&1u) || detach) state.configured=0;
    }
    if(!state.bus_invalidating && (flags&0x80000002u)==0x80000002u &&
       U8(USB_RAM)==0 && U8(USB_RAM+1)==9 && U8(USB_RAM+2)<=1 &&
       !U8(USB_RAM+3) && !U32(USB_RAM+4)) {
        state.epoch++;
        state.configured=U8(USB_RAM+2);
        state.in_busy=0;
        state.bus_invalidating=1;
    }
    if((flags&2u) && (flags&IN_COMPLETE)) state.in_busy=0;
}
void v4_out_hook(void) {
    unsigned length=OUT_LEN&511u;
    unsigned segment=EP_OUT;
    if(segment>448 || (segment&7u)) { OUT_LEN=64; return; }
    uintptr_t source=USB_RAM+segment;
    int custom=length>=5;
    for(unsigned i=0;custom && i<5;i++) custom=U8(source+i)==prefix[i];
    if(!custom && length==64) { CALL(0x9f26); return; }
    if(custom && !state.rx_ready && !state.bus_invalidating) {
        unsigned n=length>64 ? 64 : length;
        for(unsigned i=0;i<n;i++) arena.rx[i]=U8(source+i);
        for(unsigned i=n;i<64;i++) arena.rx[i]=0;
        state.rx_length=length>64 ? 65 : (uint8_t)length;
        state.rx_epoch=state.epoch;
        state.rx_time=state.ms;
        __asm__ volatile("" ::: "memory");
        state.rx_ready=1;
    }
    OUT_LEN=64;
}
static void send_reply(const uint8_t *data,uint32_t epoch,int stock) {
    unsigned flags=lock_irq();
    unsigned segment=EP_IN;
    if(segment<=448 && !(segment&7u) && state.epoch==epoch &&
       (stock || (!state.in_busy && !STOCK_READY))) {
        uintptr_t dst=USB_RAM+segment;
        for(unsigned i=0;i<64;i++) U8(dst+i)=data[i];
        /* Stock acknowledges this bit without a callback. Retire any superseded
           completion before publishing a new IN arm. */
        if(USB_INTSTS&IN_COMPLETE) USB_INTSTS=IN_COMPLETE;
        state.in_busy=1;
        IN_LEN=64;
    }
    unlock_irq(flags);
}
void v4_stock_reply(void) {
    send_reply((const uint8_t *)&U8(0x2000258c),state.epoch,1);
}
void v4_vendor_hook(void) {
    if(STOCK_READY) { CALL(0x963c); return; }
    if(!state.rx_ready) return;
    uint32_t epoch=state.rx_epoch;
    if(epoch!=state.epoch || state.ms-state.rx_time>=1000) {
        state.rx_ready=0;
        return;
    }
    if(state.in_busy) return;
    __asm__ volatile("" ::: "memory");
    respond(arena.rx,state.rx_length);
    __asm__ volatile("" ::: "memory");
    state.rx_ready=0;
    send_reply(arena.reply,epoch,0);
}

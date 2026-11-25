/* Runs the actual V4 C protocol, compositor and USB service against test MMIO. */
#define V4_TEST
#include "../firmware/v4.c"
#include <assert.h>
#include <string.h>
#include <stdio.h>

static unsigned stock_out, stock_foreground;
static void test_stock_call(unsigned address) {
    if(address==0x9f26) {
        stock_out++;
        OUT_LEN=64;
    } else if(address==0x963c) {
        stock_foreground++;
        v4_stock_reply();
        STOCK_READY=0;
    } else assert(0);
}
static uint8_t packet[64], frame_data[225];
static const uint32_t token=0x12345678;
static void request(unsigned op,unsigned arg,uint32_t t,uint16_t seq) {
    memset(packet,0,sizeof(packet));
    memcpy(packet,prefix,5);
    packet[5]=1; packet[6]=op; packet[7]=arg;
    put32(packet+8,t); put16(packet+12,seq); put16(packet+62,1);
}
static unsigned reply(void) {
    respond(packet,64);
    return arena.reply[7];
}
static void expect(unsigned op,unsigned arg,uint32_t t,uint16_t seq,unsigned expected) {
    request(op,arg,t,seq);
    assert(reply()==expected);
}
static void boot(void) {
    memset(&arena,0,sizeof(arena));
    memset(mock_stock,0,sizeof(mock_stock));
    memset(mock_usb,0,sizeof(mock_usb));
    mock_pending=mock_active=mock_suspended=0;
    mock_validation=1;
    v4_supervise();
    assert(state.mode==NATIVE && guards_ok());
    state.configured=1;
}
static void open_session(uint16_t lease,unsigned overlays) {
    request(MODE,1,token,0);
    put16(packet+14,lease);
    packet[16]=overlays;
    assert(reply()==OK && state.mode==ARMED);
}
static unsigned chunk(unsigned op,unsigned i,uint16_t seq) {
    request(op,i,token,seq);
    memcpy(packet+14,frame_data+i*48,i==4 ? 33 : 48);
    if(op==CHUNK_COMMIT) put32(packet+47,checksum(frame_data));
    return reply();
}
static unsigned do_commit(uint16_t seq,uint32_t crc) {
    request(COMMIT,0,token,seq);
    put32(packet+14,crc);
    return reply();
}
static void compose_swap(unsigned overlays) {
    uint8_t controls[4]={1,3,1,2};
    uintptr_t params[19]={0};
    params[8]=123; params[9]=2; params[10]=1;
    params[17]=(uintptr_t)controls; params[18]=2;
    assert(!v4_compose(params));
    assert(params[8]==(uintptr_t)arena.rgb);
    assert(params[9]==(overlays&1 ? 2 : 0));
    assert(params[10]==(overlays&2 ? 1 : 0));
    assert(state.controls[0]==!!(overlays&4));
    assert(state.controls[2]==!!(overlays&8));
    assert(params[18]==(overlays&12 ? 2 : 0));
    mock_pending=1;
    assert(v4_compose(params)); /* no writes into pending scanout */
    v4_supervise(); assert(state.displayed!=state.accepted || state.accepted==0);
    mock_active^=1; mock_pending=0;
    v4_supervise();
    assert(state.displayed==state.accepted && state.displayed_revision==state.queued_revision);
}
static void test_protocol(void) {
    boot();
    expect(CAPS,0,0,0,OK);
    assert(get32(arena.reply+40)==0x01160001 && arena.reply[44]==75);
    packet[5]=0; assert(reply()==OK);
    packet[5]=2; assert(reply()==BAD_VERSION);
    request(254,0,0,0); assert(reply()==BAD_OPCODE);
    request(CAPS,0,0,0);
    for(unsigned size=0;size<=65;size++) {
        if(size==64) continue;
        respond(packet,size);
        assert(arena.reply[7]==BAD_LENGTH);
    }
    packet[61]=1; assert(reply()==BAD_ARGUMENT);
    packet[61]=0; put16(packet+62,0); assert(reply()==BAD_ARGUMENT);
    expect(CHUNK,5,token,1,BAD_ARGUMENT);
    expect(CHUNK_COMMIT,0,token,1,BAD_ARGUMENT);
    expect(KEEPALIVE,0,token,0,WRONG_SESSION);
    expect(MODE,1,0,0,BAD_ARGUMENT);
    request(MODE,1,token,0); put16(packet+14,999); assert(reply()==BAD_ARGUMENT);
    open_session(1000,0);
    request(MODE,1,token,0); put16(packet+14,1000); assert(reply()==OK);
    expect(MODE,1,token,0,CONFLICT);
    expect(MODE,1,token+1,0,BUSY);
    expect(STATUS,0,token,0,OK);
    expect(KEEPALIVE,0,token,0,OK);
    assert(chunk(CHUNK,4,1)==OK);
    assert(chunk(CHUNK,4,1)==OK);
    packet[14]^=1; assert(reply()==CONFLICT);
    assert(do_commit(1,checksum(frame_data))==INCOMPLETE);
    expect(ABORT,0,token,1,OK);
    assert(!state.staged && !state.coverage);
    for(unsigned i=5;i>0;i--) assert(chunk(CHUNK,i-1,1)==OK);
    assert(do_commit(1,checksum(frame_data)^1)==BAD_CRC);
    assert(state.accepted==0 && state.committed==0);
    assert(do_commit(1,checksum(frame_data))==OK);
    assert(state.accepted==1 && state.displayed==0 && state.committed==1);
    assert(!memcmp(arena.frames[state.committed],frame_data,225));
    assert(do_commit(1,checksum(frame_data))==OK);
    assert(state.committed==1);
    assert(do_commit(1,checksum(frame_data)^1)==CONFLICT);
    expect(ABORT,0,token,1,CONFLICT);
    for(unsigned i=0;i<5;i++) assert(chunk(CHUNK,i,2)==OK);
    assert(do_commit(2,checksum(frame_data))==BUSY);
    compose_swap(0);
    assert(do_commit(2,checksum(frame_data))==OK);
    assert(state.committed==0 && state.displayed==1);
    expect(CHUNK,0,token,1,STALE_SEQUENCE);
    expect(OVERLAYS,16,token,0,UNSUPPORTED);
    expect(OVERLAYS,15,token,0,OK);
    request(BRIGHTNESS,0,token,0); put16(packet+14,0); assert(reply()==OK);
    compose_swap(15);
    for(unsigned i=0;i<225;i++) assert(!arena.rgb[i]);
    put16(packet+14,65535); assert(reply()==OK);
    /* Put the previous displayed sequence out of the way for the helper. */
    state.displayed=0;
    compose_swap(15);
    for(unsigned i=0;i<75;i++)
        for(unsigned c=0;c<3;c++) assert(arena.rgb[3*remap(i)+c]==frame_data[3*i+c]*257);
    mock_pending=1;
    expect(MODE,0,token,0,OK);
    assert(state.mode==RETURN_PENDING && v4_compose(NULL));
    mock_pending=0; v4_supervise();
    assert(state.mode==NATIVE && !v4_compose(NULL));
    expect(MODE,0,token,0,OK);
    expect(CHUNK,0,token,2,WRONG_SESSION);
}
static void test_lifecycle(void) {
    boot(); open_session(0,0);
    assert(chunk(CHUNK_COMMIT,4,1)==INCOMPLETE);
    for(unsigned i=0;i<3;i++) assert(chunk(CHUNK,i,1)==INCOMPLETE);
    assert(chunk(CHUNK,3,1)==OK && state.accepted==1);
    compose_swap(0);
    state.epoch++; v4_supervise();
    assert(state.mode==NATIVE && !state.token);
    boot(); state.ms=UINT32_MAX-400; open_session(1000,0);
    assert(chunk(CHUNK,1,1)==OK);
    state.ms+=999; v4_supervise();
    assert(state.token && state.coverage);
    v4_tick(); v4_supervise(); assert(!state.token && !state.coverage);
    boot(); open_session(0,0);
    assert(chunk(CHUNK,0,1)==OK);
    state.ms+=1000; v4_supervise(); assert(state.token && !state.coverage);
    state.ms+=1000; v4_supervise(); assert(!state.token);
    boot(); open_session(0,0);
    state.accepted=state.displayed=65534;
    for(unsigned i=0;i<5;i++) assert(chunk(CHUNK,i,65535)==OK);
    assert(do_commit(65535,checksum(frame_data))==OK);
    expect(CHUNK,0,token,0,BAD_ARGUMENT);
    expect(CHUNK,0,token,1,STALE_SEQUENCE);
    mock_suspended=1; v4_supervise(); assert(!state.token);
    boot(); open_session(0,0);
    arena.rgb[225]=0;
    v4_supervise(); assert(!state.token && state.fault);
    expect(MODE,1,token,0,INTERNAL_FAULT);
    boot(); assert(!state.fault);
    open_session(0,0);
    state.committed=255;
    expect(CHUNK,0,token,1,INTERNAL_FAULT);
    assert(state.fault && !state.token && !state.accepted);
    boot(); open_session(0,0);
    state.mode=ENTER_PENDING;
    state.committed=255;
    mock_pending=1;
    assert(v4_compose(NULL)==1 && state.fault && !state.token);
    mock_pending=0;
    assert(v4_compose(NULL)==0);
}
static void test_orders(unsigned order[5],unsigned depth,unsigned used) {
    if(depth!=5) {
        for(unsigned i=0;i<5;i++) {
            if(used&(1u<<i)) continue;
            order[depth]=i;
            test_orders(order,depth+1,used|(1u<<i));
        }
        return;
    }
    for(unsigned fast=0;fast<2;fast++) {
        boot(); open_session(0,0);
        for(unsigned i=0;i<5;i++) {
            unsigned index=order[i];
            unsigned status=chunk(fast && index==4 ? CHUNK_COMMIT : CHUNK,index,1);
            assert(status==OK || (fast && status==INCOMPLETE));
        }
        if(!fast) {
            assert(!state.accepted);
            assert(do_commit(1,checksum(frame_data))==OK);
        }
        assert(state.accepted==1 && !memcmp(arena.frames[state.committed],frame_data,225));
    }
}
static void test_usb(void) {
    boot();
    EP_OUT=80; EP_IN=16;
    request(CAPS,0,0,0);
    memcpy((void *)&U8(USB_RAM+80),packet,64);
    OUT_LEN=7; v4_out_hook(); assert(state.rx_ready && state.rx_length==7 && OUT_LEN==64);
    v4_vendor_hook();
    assert(IN_LEN==64 && state.in_busy && U8(USB_RAM+16+7)==BAD_LENGTH);
    USB_INTSTS=2|IN_COMPLETE; v4_usb_event(); assert(!state.in_busy);
    USB_INTSTS=0;
    OUT_LEN=64; v4_out_hook(); assert(state.rx_ready);
    state.in_busy=1; v4_vendor_hook(); assert(state.rx_ready);
    state.ms+=1000; v4_vendor_hook(); assert(!state.rx_ready);
    USB_INTSTS=1; USB_ATTR=1; v4_usb_event();
    assert(!state.configured && !state.in_busy);
    USB_INTSTS=0x80000002; U8(USB_RAM+1)=9; U8(USB_RAM+2)=1;
    v4_usb_event(); assert(state.configured);
    U8(USB_RAM+2)=0; v4_usb_event(); assert(!state.configured);
    USB_INTSTS=0; v4_usb_event();
    memset(arena.reply,0xA5,64);
    memset((void *)&U8(USB_RAM+16),0x5A,64);
    IN_LEN=0;
    send_reply(arena.reply,state.epoch-1,0);
    for(unsigned i=0;i<64;i++) assert(U8(USB_RAM+16+i)==0x5A);
    assert(IN_LEN==0);
    state.in_busy=1;
    send_reply(arena.reply,state.epoch,0);
    for(unsigned i=0;i<64;i++) assert(U8(USB_RAM+16+i)==0x5A);
    assert(IN_LEN==0);
    U8(USB_RAM+80)=1; OUT_LEN=64;
    v4_out_hook(); assert(stock_out==1);
    STOCK_READY=1; v4_vendor_hook(); assert(stock_foreground==1 && !STOCK_READY);
}
static void test_consecutive_frames(void) {
    uint32_t random=UINT32_C(0xd0c42026);
    boot(); open_session(0,0);
    for(uint16_t sequence=1;sequence<=2000;sequence++) {
        for(unsigned i=0;i<FRAME_BYTES;i++) {
            random^=random<<13;
            random^=random>>17;
            random^=random<<5;
            frame_data[i]=(uint8_t)random;
        }
        unsigned overlays=sequence&OVERLAY_MASK;
        expect(OVERLAYS,overlays,token,0,OK);
        for(unsigned i=0;i<5;i++) {
            unsigned index=(sequence+i*2)%5;
            assert(chunk(CHUNK,index,sequence)==OK);
            if(i==0) assert(chunk(CHUNK,index,sequence)==OK);
        }
        assert(do_commit(sequence,checksum(frame_data))==OK);
        assert(!memcmp(arena.frames[state.committed],frame_data,FRAME_BYTES));
        compose_swap(overlays);
        assert(guards_ok());
    }
}
int main(void) {
    for(unsigned i=0;i<225;i++) frame_data[i]=(uint8_t)(i*37+11);
    test_protocol();
    test_lifecycle();
    unsigned order[5];
    test_orders(order,0,0);
    test_usb();
    test_consecutive_frames();
    for(unsigned c=0;c<256;c++)
        for(unsigned b=0;b<65536;b++)
            assert(scale(c,b)==(c*257u*b+32767u)/65535u);
    puts("actual V4 C protocol, compositor, timers, USB mock and exhaustive scaling passed");
}

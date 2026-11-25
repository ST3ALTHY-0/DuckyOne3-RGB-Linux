// Runs an offline wire-to-scanout transaction using the generated Thumb image.
// @category Ducky
import ghidra.app.emulator.AdaptedEmulator;
import ghidra.app.emulator.Emulator;
import ghidra.app.emulator.EmulatorHelper;
import ghidra.app.script.GhidraScript;
import ghidra.pcode.emulate.BreakCallBack;
import ghidra.pcode.pcoderaw.PcodeOpRaw;
import ghidra.program.model.address.AddressSet;
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Random;
import java.util.zip.CRC32;

public class EmulateDuckyV4 extends GhidraScript {
    private static final long RAM = 0x20000000L;
    private static final long USB = 0x40060000L;
    private static final long INITIAL_SP = RAM + 0x818;
    private static final long SP = RAM + 0x7E0;
    private static final int STOP = 0xA54C;
    private EmulatorHelper vm;
    private long primask;

    private static void require(boolean condition, String evidence) {
        if (!condition) throw new AssertionError(evidence);
    }

    private void put(long address, int size, long value) {
        vm.writeMemoryValue(toAddr(address), size, value);
    }

    private int u8(long address) {
        return Byte.toUnsignedInt(vm.readMemoryByte(toAddr(address)));
    }

    private static void putPacket(byte[] p, int offset, int count, long word) {
        for (int i = 0; i < count; i++) p[offset+i] = (byte)(word >> (8*i));
    }

    private void compose() throws Exception {
        vm.writeRegister("r0", RAM+0x1770);
        vm.writeRegister("r1", 2);
        vm.writeRegister("r2", 0);
        vm.writeRegister("r3", 1);
        put(SP, 4, RAM+0x1364);
        put(SP+4, 4, RAM+0x2670);
        put(SP+8, 4, 0);
        runAt(0x3B08, STOP);
    }

    private void display() throws Exception {
        compose();
        require(u8(RAM+0x27B3) == 1, "Missing pending page");
        finishScan();
        runAt(0x8E92, 0x321C);
    }

    private void finishScan() throws Exception {
        put(RAM+0x27A8, 1, 0); // Model the SPI ISR finishing the preceding transfer.
        put(RAM+0x27AB, 1, 4);
        runAt(0x3A18, STOP);
    }

    private void runAt(long entry, long stop) throws Exception {
        var saved = new BigInteger[8];
        for (int i = 0; i < saved.length; i++) saved[i] = vm.readRegister("r"+(4+i));
        vm.writeRegister("lr", STOP | 1);
        long stack = entry == 0xA47C ? INITIAL_SP : SP;
        vm.writeRegister(vm.getStackPointerRegister(), stack);
        vm.setContextRegister(currentProgram.getRegister("TMode"), BigInteger.ONE);
        vm.setBreakpoint(toAddr(stop));
        try {
            require(vm.run(toAddr(entry), null, monitor), "Emulator " + vm.getLastError());
            require(vm.getExecutionAddress().equals(toAddr(stop)), "Unexpected return address");
            require(vm.readRegister(vm.getStackPointerRegister()).longValue() == stack,
                    "Unbalanced stack after entry " + Long.toHexString(entry));
            if (entry != 0xA47C)
                for (int i = 0; i < saved.length; i++)
                    require(saved[i].equals(vm.readRegister("r"+(4+i))),
                            "Nonvolatile r" + (4+i) + " at " + Long.toHexString(entry));
        } finally {
            vm.clearBreakpoint(toAddr(stop));
        }
    }

    private void usbEvent(long flags) throws Exception {
        put(USB+4, 4, flags);
        long vector = 0;
        for (int i = 0; i < 4; i++) vector |= (long)u8(0x9C+i) << (8*i);
        runAt(vector & ~1L, 0x9E00);
        put(USB+4, 4, 0);
    }

    private byte[] exchange(int opcode, int arg, int seq, long token, byte[] data, int length)
            throws Exception {
        byte[] packet = new byte[64];
        byte[] magic = {0, 0x3A, 0x52, 0x34, (byte)0xE4};
        System.arraycopy(magic, 0, packet, 0, magic.length);
        packet[5] = 1;
        packet[6] = (byte)opcode;
        packet[7] = (byte)arg;
        putPacket(packet, 8, 4, token);
        putPacket(packet, 12, 2, seq);
        System.arraycopy(data, 0, packet, 14, data.length);
        putPacket(packet, 62, 2, 0x1234);
        vm.writeMemory(toAddr(USB+0x150), packet);
        put(USB+0x534, 4, length);
        usbEvent(2 | (1 << 19));
        runAt(0x9ED8, 0x9EDC);
        require(u8(USB+0x534) == 64, "OUT did not rearm");
        long inputMask = primask;
        runAt(0x8E96, 0x8E9A);
        require(primask == inputMask, "Vendor reply failed to restore PRIMASK");
        byte[] reply = vm.readMemory(toAddr(USB+0x110), 64);
        require(Arrays.equals(magic, Arrays.copyOf(reply, 5)), "No V4 reply");
        require(Byte.toUnsignedInt(reply[6]) == (opcode | 128), "Reply opcode");

        // Model vendor IN completion via the generated vector before stock acknowledges it.
        usbEvent(2 | (1 << 18));
        return reply;
    }

    @Override
    protected void run() throws Exception {
        vm = new EmulatorHelper(currentProgram) {
            @Override
            protected Emulator newEmulator() { return new AdaptedEmulator(this); }
        };
        vm.registerCallOtherCallback("isIRQinterruptsEnabled", new BreakCallBack() {
            @Override public boolean pcodeCallback(PcodeOpRaw op) {
                vm.getEmulator().getMemState().setValue(op.getOutput(), primask);
                return true;
            }
        });
        vm.registerCallOtherCallback("disableIRQinterrupts", new BreakCallBack() {
            @Override public boolean pcodeCallback(PcodeOpRaw op) {
                primask = 1;
                return true;
            }
        });
        vm.registerCallOtherCallback("enableIRQinterrupts", new BreakCallBack() {
            @Override public boolean pcodeCallback(PcodeOpRaw op) {
                primask = 0;
                return true;
            }
        });
        try {
            for (int i = 0; i < 13; i++) vm.writeRegister("r"+i, 0);
            byte[] initial = new byte[0x5000];
            Random random = new Random(0xD0C42026L);
            random.nextBytes(initial);
            vm.writeMemory(toAddr(RAM), initial);
            vm.writeMemory(toAddr(USB), new byte[0x600]);
            runAt(0xA47C, STOP);
            require(u8(RAM+0x414) == Byte.toUnsignedInt(initial[0x414]), "Initialized data overran");
            for (int i = 0x818; i < 0x2D20; i++)
                require(u8(RAM+i) == 0, "Unexpected initialized byte at " + Integer.toHexString(i));
            require(u8(RAM+0x2D20) == Byte.toUnsignedInt(initial[0x2D20]), "Zero initialization overran");

            vm.writeMemory(toAddr(0x40030000L), new byte[0x100]);
            vm.writeMemory(toAddr(0x50000000L), new byte[0x100]);
            vm.writeMemory(toAddr(0xE000E100L), new byte[0x100]);
            vm.enableMemoryWriteTracking(true);
            put(RAM+0x269E, 1, 1);
            put(USB+0x520, 4, 16);
            put(USB+0x530, 4, 80);
            put(USB+0x101, 1, 9); // SET_CONFIGURATION
            put(USB+0x102, 1, 1);
            usbEvent(0x80000002L);
            runAt(0x8E92, 0x321C);
            require(exchange(1, 0, 0, 0, new byte[0], 7)[7] == 1, "Short OUT accepted");
            primask = 1;
            require(exchange(1, 0, 0, 0, new byte[0], 64)[7] == 0, "CAPS failed");
            primask = 0;
            long token = 0x12345678;
            require(exchange(2, 1, 0, token, new byte[3], 64)[7] == 0, "External mode failed");
            byte[] frame = new byte[225];
            for (int i = 0; i < frame.length; i++) frame[i] = (byte)(i * 23);
            for (int i = 4; i >= 0; i--) {
                byte[] chunk = Arrays.copyOfRange(frame, i*48, Math.min((i+1)*48, 225));
                require(exchange(3, i, 1, token, chunk, 64)[7] == 0, "Chunk failed");
            }
            CRC32 crc = new CRC32();
            crc.update(frame);
            byte[] check = new byte[4];
            putPacket(check, 0, 4, crc.getValue());
            byte[] commit = exchange(4, 0, 1, token, check, 64);
            require(commit[7] == 0 && commit[18] == 1 && commit[22] == 0, "Commit state");

            compose();
            require(u8(RAM+0x27B3) == 1 && u8(RAM+0x27B2) == 0, "Publication state");
            long back = RAM + 0x0E18 + 450;
            for (int i = 0; i < frame.length; i++)
                require(u8(back+2*i) == Byte.toUnsignedInt(frame[i]) &&
                        u8(back+2*i+1) == Byte.toUnsignedInt(frame[i]), "RGB16/remap at " + i);
            finishScan();
            require(u8(RAM+0x27B3) == 0 && u8(RAM+0x27B2) == 1, "Stock timer swap");
            runAt(0x8E92, 0x321C);
            require(exchange(5, 0, 0, token, new byte[0], 64)[22] == 1, "Displayed status");
            require(exchange(2, 0, 0, token, new byte[0], 64)[7] == 0, "Restore native");
            put(RAM+0x1770, 2, 0x1234);
            runAt(0x8E92, 0x8E96);
            require(u8(RAM+0x0E18) == 0x34 && u8(RAM+0x0E19) == 0x12,
                    "Native compositor source was not restored");
            finishScan();
            int transactions = getScriptArgs().length == 0 ? 32 : Integer.parseInt(getScriptArgs()[0]);
            for (int i = 0; i < transactions; i++) {
                int seq = i % 64 + 1;
                long session = token + 1 + i / 64;
                if (seq == 1) {
                    require(exchange(2, 1, 0, session, new byte[3], 64)[7] == 0, "Reopen");
                }
                int overlay = i & 15;
                require(exchange(8, overlay, 0, session, new byte[0], 64)[7] == 0, "Overlay");
                require(exchange(7, 0, 0, session, new byte[] {-1, -1}, 64)[7] == 0, "Brightness");
                byte[] bad = new byte[random.nextInt(49)];
                random.nextBytes(bad);
                require(exchange(3, 5+random.nextInt(251), seq, session, bad, 64)[7] == 4,
                        "Invalid chunk accepted");
                require(exchange(3, 0, seq, session, bad, 7+random.nextInt(57))[7] == 1,
                        "Random short report accepted");
                require(exchange(4, 0, seq, session, new byte[4], 64)[7] == 8, "Incomplete commit");
                random.nextBytes(frame);
                for (int j = 0; j < 5; j++) {
                    int part = (i + j*2) % 5;
                    byte[] chunk = Arrays.copyOfRange(frame, part*48, Math.min((part+1)*48, 225));
                    require(exchange(3, part, seq, session, chunk, 64)[7] == 0, "Staging");
                    if(j == 0) require(exchange(3, part, seq, session, chunk, 64)[7] == 0, "Duplicate");
                }
                crc.reset();
                crc.update(frame);
                putPacket(check, 0, 4, crc.getValue());
                require(exchange(4, 0, seq, session, check, 64)[7] == 0, "Stress commit " + i);
                display();
                require(Byte.toUnsignedInt(exchange(5, 0, 0, session, new byte[0], 64)[22]) == seq,
                        "Stress displayed " + i);
                if (seq == 64 || i == transactions-1) {
                    require(exchange(2, 0, 0, session, new byte[0], 64)[7] == 0, "Close");
                    runAt(0x8E92, 0x321C);
                }
                if ((i+1)%256 == 0) {
                    println("Verified " + (i+1) + " staged, committed and displayed frames");
                    monitor.checkCancelled();
                }
            }
            println("Random seed 0xD0C42026, committed and displayed frames: " + transactions);
            long lifecycleSession = token + transactions + 1;
            require(exchange(2, 1, 0, lifecycleSession, new byte[] {(byte)0xE8, 3, 0}, 64)[7] == 0,
                    "Leased session");
            require(exchange(3, 0, 1, lifecycleSession, new byte[48], 64)[7] == 0, "Lease stage");
            put(RAM+0x2C2C, 4, 999);
            runAt(0x8E92, 0x321C);
            require(exchange(5, 0, 0, 0, new byte[0], 64)[14] == 1, "Lease expired early");
            put(RAM+0x2C2C, 4, 1000);
            runAt(0x8E92, 0x321C);
            require(exchange(2, 0, 0, lifecycleSession, new byte[0], 64)[7] == 0, "Lease fallback");
            runAt(0x8E92, 0x321C);
            lifecycleSession++;
            require(exchange(2, 1, 0, lifecycleSession, new byte[3], 64)[7] == 0, "Open before suspend");
            put(USB+0x10, 4, 2);
            usbEvent(1);
            runAt(0x8E92, 0x321C);
            require(exchange(5, 0, 0, 0, new byte[0], 64)[14] == 0, "Suspend did not revoke mode");
            put(USB+0x10, 4, 4);
            usbEvent(1);
            runAt(0x8E92, 0x321C);
            require(exchange(2, 1, 0, lifecycleSession, new byte[3], 64)[7] == 0, "Open after resume");
            put(RAM+0x2C4C, 2, 65535); // Accepted sequence at exhaustion.
            require(exchange(3, 0, 0, lifecycleSession, new byte[48], 64)[7] == 4, "Zero sequence");
            require(exchange(3, 0, 1, lifecycleSession, new byte[48], 64)[7] == 11, "Wrapped sequence");
            vm.writeRegister("r0", 1);
            runAt(0x5B2A, 0x8930);
            require(vm.readRegister("r0").intValue() == 1, "Reset argument changed");
            runAt(0x8E92, 0x321C);
            long faultSession = lifecycleSession + 1;
            require(exchange(2, 1, 0, faultSession, new byte[3], 64)[7] == 0, "Fault test open");
            put(RAM+0x2C43, 1, 255); // Arena state + committed byte.
            require(exchange(3, 0, 1, faultSession, new byte[48], 64)[7] == 13,
                    "Invalid frame selector reached command");
            runAt(0x8E92, 0x321C);
            require(exchange(2, 1, 0, faultSession+1, new byte[3], 64)[7] == 13, "Fault not latched");
            // Exercise a real native mode change and a compositor profile input
            // after fault fallback, with the normal scheduler dispatch enabled.
            put(RAM+0x2680, 1, 12);
            put(RAM+0x1938, 4, 0x2313); // Stock mode-zero init function.
            put(RAM+0x1364, 1, 1);
            put(RAM+0x1365, 2, 0x0FFF);
            put(RAM+0x1770, 2, 0x2345);
            put(RAM+0x27B0, 1, 1);
            runAt(0x8E92, 0x8E96);
            require(u8(RAM+0x2680) == 0 && u8(RAM+0x1770) == 0 && u8(RAM+0x2438) == 2,
                    "Native mode initialization did not run");
            require(u8(RAM+0x27B3) == 1, "Native profile renderer did not publish");
            require(u8(RAM+0x2D20) == Byte.toUnsignedInt(initial[0x2D20]), "Extension interfered past reservation");
            AddressSet allowed = new AddressSet();
            allowed.addRange(toAddr(RAM+0x414), toAddr(INITIAL_SP-1));
            allowed.addRange(toAddr(RAM+0x0E18), toAddr(RAM+0x119B));
            allowed.addRange(toAddr(RAM+0x1364), toAddr(RAM+0x1366));
            allowed.addRange(toAddr(RAM+0x1770), toAddr(RAM+0x1931));
            allowed.addRange(toAddr(RAM+0x1938), toAddr(RAM+0x193B));
            allowed.addRange(toAddr(RAM+0x1BD0), toAddr(RAM+0x1D91));
            allowed.addRange(toAddr(RAM+0x2438), toAddr(RAM+0x2482));
            allowed.addRange(toAddr(RAM+0x2670), toAddr(RAM+0x269E));
            allowed.addRange(toAddr(RAM+0x27A8), toAddr(RAM+0x27BF));
            allowed.addRange(toAddr(RAM+0x2820), toAddr(RAM+0x2D1F));
            allowed.addRange(toAddr(USB), toAddr(USB+0x5FF));
            allowed.addRange(toAddr(0x40030000L), toAddr(0x400300FFL));
            allowed.addRange(toAddr(0x50000000L), toAddr(0x500000FFL));
            allowed.addRange(toAddr(0xE000E100L), toAddr(0xE000E1FFL));
            AddressSet writes = new AddressSet();
            for (var range : vm.getTrackedMemoryWriteSet()) {
                if (range.getMinAddress().isMemoryAddress()) writes.add(range);
            }
            require(allowed.contains(writes), "Unexpected writes " + writes.subtract(allowed));
            println("Tracked memory spans: " + writes);
            var stackWrites = writes.intersectRange(toAddr(RAM+0x414), toAddr(INITIAL_SP-1));
            println("Lowest RAM stack write in this transaction: " + stackWrites.getMinAddress());
            println("V4 THUMB EMULATION PASSED");
        } finally {
            vm.dispose();
        }
    }
}

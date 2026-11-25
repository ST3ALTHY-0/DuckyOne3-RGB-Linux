// Independently decode the installed hooks and reachable extension in the raw image.
// @category Ducky
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;
import java.math.BigInteger;
import java.nio.file.Files;
import java.nio.file.Path;

public class AuditDuckyV4 extends GhidraScript {
    private static final long BASE = 0xA7C0;
    private static final int[] HOOKS = {0x3B0C, 0x52F8, 0x5B2A, 0x8E92, 0x8E96, 0x964A, 0x9ED8};
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
    private int word(long address) throws Exception {
        return currentProgram.getMemory().getInt(toAddr(address));
    }
    private Instruction decode(long address, AddressSet allowed) throws Exception {
        var target = toAddr(address);
        var known = currentProgram.getListing().getInstructionAt(target);
        if (known != null) return known;
        currentProgram.getProgramContext().setValue(
            currentProgram.getRegister("TMode"), target, target, BigInteger.ONE);
        var command = new DisassembleCommand(target, allowed, true);
        check(command.applyTo(currentProgram, monitor), "Disassembly failed at " + target);
        var instruction = currentProgram.getListing().getInstructionAt(target);
        check(instruction != null, "No instruction at " + target);
        return instruction;
    }
    @Override
    protected void run() throws Exception {
        var stock = Files.readAllBytes(Path.of(getScriptArgs()[0]));
        long end = currentProgram.getMaxAddress().getOffset()+1;
        check(stock.length == 0xA7BE && end > BASE && end <= 0xC7C0, "Unexpected image bounds");
        for (int i = 0; i < stock.length; i++) {
            boolean patched = (i >= 0x9C && i < 0xA0) || (i >= 0xA4A8 && i < 0xA4AC);
            for (int hook : HOOKS) patched |= i >= hook && i < hook+4;
            check(patched || stock[i] == currentProgram.getMemory().getByte(toAddr(i)),
                "Unexpected byte at " + toAddr(i));
        }
        check(currentProgram.getMemory().getShort(toAddr(0xA7BE)) == -1, "Alignment fill");
        check(word(0xA4A8) == 0x2508 && word(0xA4AC) == 0x20000818, "Scatter descriptor");
        var extent = new AddressSet(toAddr(BASE), toAddr(end-1));
        int vector = word(0x9C);
        check((vector&1) == 1 && extent.contains(toAddr(vector&~1)), "Vector Thumb pointer");
        decode(vector&~1, extent);
        for (int address : HOOKS) {
            var instruction = decode(address, new AddressSet(toAddr(address), toAddr(address+3)));
            var flows = instruction.getFlows();
            check(instruction.getLength() == 4 && instruction.getMnemonicString().equals("bl") &&
                flows.length == 1 && extent.contains(flows[0]), "Invalid hook " + instruction);
            println(toAddr(address) + " " + instruction);
            decode(flows[0].getOffset(), extent);
        }
        // The vendor opcode switch bounds r1 to 0..7, then indexes unsigned
        // halfword offsets encoded as bytes. Thumb ADD pc reads address+4.
        var jump = currentProgram.getListing().getInstructionAt(toAddr(0xAFBA));
        check(jump != null && jump.toString().equals("add pc,r1"), "Vendor jump table changed");
        for (int i = 0; i < 8; i++) {
            int offset = Byte.toUnsignedInt(currentProgram.getMemory().getByte(toAddr(0xAFBC+i)));
            long target = 0xAFBE + 2L*offset;
            decode(target, extent);
            println("Vendor table entry " + i + " -> " + toAddr(target));
        }
        var instructions = new AddressSet();
        var literals = new AddressSet();
        var rows = currentProgram.getListing().getInstructions(extent, true);
        int count = 0, direct = 0;
        while (rows.hasNext()) {
            var instruction = rows.next();
            instructions.addRange(instruction.getMinAddress(), instruction.getMaxAddress());
            for (var target : instruction.getFlows()) {
                check(extent.contains(target) &&
                    currentProgram.getListing().getInstructionAt(target) != null,
                    "Direct branch misses instruction " + instruction.getAddress() + " -> " + target);
                direct++;
            }
            if(instruction.getMnemonicString().equals("ldr") && instruction.getNumOperands() == 2) {
                for (var object : instruction.getOpObjects(1)) {
                    if (!(object instanceof Address literal)) continue;
                    check(extent.contains(literal, literal.add(3)) && (literal.getOffset() & 3)==0,
                        "Invalid literal address at " + instruction.getAddress());
                    literals.addRange(literal, literal.add(3));
                }
            }
            println(instruction.getAddress() + " " + instruction);
            count++;
        }
        check(!instructions.intersects(literals), "Literal overlaps instructions");
        long[] slots = {0xA81C, 0xA820, 0xA824, 0xA828, 0xA82C, 0xAD3C, 0xAFC8};
        int[] exits = {0x321D, 0x8931, 0x5747, 0x9E01, 0x3F8F, 0x9F27, 0x963D};
        for (int i = 0; i < slots.length; i++) {
            check(literals.contains(toAddr(slots[i])) && word(slots[i]) == exits[i],
                "Stock continuation mismatch " + toAddr(slots[i]));
            decode(exits[i]&~1, new AddressSet(toAddr(exits[i]&~1), toAddr((exits[i]&~1)+3)));
            println("Stock address literal " + toAddr(slots[i]) + " -> " + toAddr(exits[i]));
        }
        println("AUDIT decoded " + count + " instructions, " + direct + " direct flows, "
            + literals.getNumAddresses()/4 + " literal words. Remaining data/padding "
            + extent.subtract(instructions).subtract(literals));
    }
}

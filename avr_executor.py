import sys

class Executor(object):
    
    ip = 0
    sp = 0
    flag_i = 0
    flag_t = 0
    flag_h = 0
    flag_s = 0
    flag_v = 0
    flag_n = 0
    flag_z = 0
    flag_c = 0
    flag_names = 'cznvshti'
    
    def __init__(self, code):
        self.peripherals = Peripherals(self)
        self.words = [0] * 4096
        if len(code) > len(self.words):
            raise Exception("Code is longer than 8K")
        for i in range(len(code)):
            self.words[i] = code[i]
        self.regs = [0] * 32
        self.ram = [0] * 1024
        self.ram_min_address = 64 + 32
        self.ram_max_address = 1024 + 64 + 32 - 1
    
    def step(self):
        w = self.words[self.ip]
        w3 = w >> 12
        if w3 == 0b0000:
            self.i_0000(w)
        elif w3 == 0b0001:
            self.i_0001(w)
        elif w3 == 0b0010:
            self.i_0010(w)
        elif w3 == 0b0011:
            self.i_cpi(w)
        elif (w3 & 0xE) == 0b0100:
            self.i_subi(w)
        elif (w3 & 0xE) == 0b0110:
            self.i_bitwiseim(w)
        elif w3 == 0b1001:
            self.i_1001(w)
        elif w3 == 0b1011:
            self.i_in_out(w)
        elif w3 == 0b1100:
            self.i_rjmp(w)
        elif w3 == 0b1101:
            self.i_rjmp(w, True)
        elif w3 == 0b1110:
            self.i_ldi(w)
        elif w3 == 0b1111:
            self.i_1111(w)
        else:
            self.not_implemented(w)
        self.ip += 1
    
    def run(self):
        while self.words[self.ip] != 0:
            self.step()
    
    def printRegs(self):
        for i in range(0, 16):
            print "%02X" % self.regs[i],
        print
        for i in range(16, 32):
            print "%02X" % self.regs[i],
        print
        print "ip=%04X, sp=%04X" % (self.ip, self.sp)
        print "flags:", self.flagStr('i'), self.flagStr('t'), \
            self.flagStr('h'), self.flagStr('s'), \
            self.flagStr('v'), self.flagStr('n'), \
            self.flagStr('z'), self.flagStr('c')
    
    def flagStr(self, c):
        v = getattr(self, 'flag_' + c)
        return c.upper() if v == 1 else '-'
    
    def i_0000(self, w):
        w2h = (w >> 10) & 0x03
        if w2h == 1:
            self.i_cp(w, True)
        elif w2h == 3:
            self.i_add(w)
        elif w2h == 2:
            self.i_sub(w, True)
        else:
            self.not_implemented(w)
        
    def i_0001(self, w):
        w2h = (w >> 10) & 0x03
        if w2h == 0:
            self.i_cpse(w)
        elif w2h == 1:
            self.i_cp(w)
        elif w2h == 2:
            self.i_sub(w)
        elif w2h == 3:
            self.i_add(w, True)
        else:
            self.not_implemented(w)
        
    def i_0010(self, w):
        w2h = (w >> 10) & 0x03
        if w2h == 3:
            self.i_mov(w)
        elif w2h == 0:
            self.i_bitwise(w, 'and')
        elif w2h == 1:
            self.i_bitwise(w, 'eor')
        elif w2h == 2:
            self.i_bitwise(w, 'or')
    
    def i_1001(self, w):
        c, r = self.code7_reg5(w)
        if c >> 4 == 2:
            self.i_1001_010(c, r)
        elif c == 0x1F:
            self.i_push_pop(r, -1)
        elif c == 0x0F:
            self.i_push_pop(r, 1)
        elif (c & 0x7E) == 4:
            self.i_lpm(r, c & 1)
        elif w & 0xF0F == 0x408:
            self.set_sreg(r & 7, (r >> 3) ^ 1)
        else:
            self.not_implemented(w)
    
    def i_1001_010(self, c, r):
        if c == 0x23:
            self.i_inc_dec(r, 1)
        elif c == 0x2A:
            self.i_inc_dec(r, -1)
        elif c == 0x28 and r == 0x1C:
            self.i_lpm(0, 0)
        elif c == 0x28 and r == 0x10:
            self.i_ret()
        elif c & 0xE == 0:
            self.i_com_neg(r, c & 1)
        elif c == 0x22:
            self.i_swap(r)
        elif c & 7 > 4:
            self.i_shift_right(r, c & 3)
        else:
            self.not_implemented(w)
    
    def i_1111(self, w):
        c, k = self.code5_const7(w)
        if c & 0x10 != 0:
            self.not_implemented(w)
        self.branch(k, c & 7, c >> 3)
    
    def i_add(self, w, with_carry = False):
        d, r = self.dest5_src5(w)
        a = self.regs[d]
        b = self.regs[r]
        res = (a + b + (self.flag_c if with_carry else 0)) & 0xFF
        self.set_flags_hvc(a, b, res)
        self.set_flags_nsz(res)
        self.regs[d] = res
    
    def i_sub(self, w, with_carry = False):
        d, r = self.dest5_src5(w)
        self.regs[d] = self.subtract(d, self.regs[r], with_carry)
    
    def i_subi(self, w, with_carry = False):
        r, k = self.dest4_const(w)
        self.regs[r] = self.subtract(r, k, with_carry)
    
    def i_cp(self, w, with_carry = False):
        d, r = self.dest5_src5(w)
        self.subtract(d, self.regs[r], with_carry)
    
    def i_cpi(self, w):
        r, k = self.dest4_const(w)
        self.subtract(r, k, False)
    
    def i_cpse(self, w):
        d, r = self.dest5_src5(w)
        if self.regs[d] == self.regs[r]:
            next_code_size = self.instruction_size(self.words[self.ip + 1])
            self.ip += next_code_size
    
    def subtract(self, rd, b, with_carry):
        a = self.regs[rd]
        res = (a - b - (self.flag_c if with_carry else 0)) & 0xFF
        self.set_flags_hvc(res, b, a)
        prev_z = self.flag_z
        self.set_flags_nsz(res)
        if with_carry:
            self.flag_z &= prev_z
        return res
    
    def i_com_neg(self, r, c):
        a = 0xFF + c
        b = self.regs[r]
        res = (a - b) & 0xFF
        self.regs[r] = res
        self.set_flags_hvc(res, b, a)
        self.set_flags_nsz(res)
        self.flag_c = 1 if c == 0 or res != 0 else 0
    
    def i_shift_right(self, r, c):
        v = self.regs[r]
        hbit = 0 if c == 2 else (self.flag_c if c == 3 else v >> 7)
        self.flag_c = v & 1
        self.flag_n = hbit
        self.flag_v = self.flag_n ^ self.flag_c
        self.flag_s = self.flag_n ^ self.flag_v
        v = (v >> 1) + (hbit << 7)
        print "hbit %s" % hbit
        self.flag_z = 1 if v == 0 else 0
        self.regs[r] = v
    
    def i_inc_dec(self, r, k):
        o = self.regs[r]
        v = (o + k) & 0xFF
        self.regs[r] = v
        self.flag_v = 1 if (k == 1 and o == 0x7F) or (k == -1 and o == 0x80) else 0
        self.set_flags_nsz(v)
    
    def i_bitwise(self, w, op):
        d, r = self.dest5_src5(w)
        a = self.regs[d]
        b = self.regs[r]
        if op == 'and':
            a &= b
        elif op == 'eor':
            a ^= b
        else:
            a |= b
        self.set_flags_bitwise(a)
        self.regs[d] = a
    
    def i_bitwiseim(self, w):
        r, k = self.dest4_const(w)
        v = self.regs[r]
        if w & 0x1000 != 0:
            v &= k
        else:
            v |= k
        self.set_flags_bitwise(v)
        self.regs[r] = v
    
    def i_in_out(self, w):
        d = (w >> 11) & 0x01
        a = ((w >> 5) & 0x30) | (w & 0xF)
        r = (w >> 4) & 0x1F
        if d == 1:
            self.peripherals.write(a, self.regs[r])
        else:
            self.regs[r] = self.peripherals.read(a)
    
    def i_swap(self, r):
        v = self.regs[r]
        self.regs[r] = (v >> 4) + ((v & 0xF) << 4)
    
    def i_ldi(self, w):
        r, k = self.dest4_const(w)
        self.regs[r] = k
    
    def i_mov(self, w):
        d, r = self.dest5_src5(w)
        self.regs[d] = self.regs[r]
    
    def i_push_pop(self, r, spinc):
        if spinc < 0:
            self.stack_operation(self.regs[r])
        else:
            self.regs[r] = self.stack_operation()
    
    def i_lpm(self, r, zinc):
        addr = self.regs[31] * 256 + self.regs[30]
        self.regs[r] = (self.words[addr >> 1] >> ((addr & 1) * 8)) & 0xFF
        if zinc != 0:
            addr += 1
            self.regs[30] = addr & 0xFF
            self.regs[31] = (addr >> 8) & 0xFF
    
    def i_rjmp(self, w, is_call = False):
        if is_call:
            retaddr = self.ip + 1
            self.stack_operation(retaddr & 0xFF)
            self.stack_operation((retaddr >> 8) & 0xFF)
        offset = w & 0xFFF
        self.ip += offset if offset & 0x800 == 0 else (offset - 0x1000)
    
    def i_ret(self):
        pch = self.stack_operation()
        pcl = self.stack_operation()
        self.ip = pch * 256 + pcl - 1
    
    def stack_operation(self, v = None):
        if v is None:
            self.sp_inc(1)
            return self.get_ram(self.sp)
        else:
            self.set_ram(self.sp, v)
            self.sp_inc(-1)
    
    def branch(self, offs, bit, v):
        if v != self.get_sreg(bit):
            self.ip += offs if offs < 64 else offs - 128
    
    def sp_inc(self, v):
        self.sp += v
        if self.sp < self.ram_min_address:
            raise Exception("Stack overflow")
        elif self.sp > self.ram_max_address:
            raise Exception("Stack underflow")
    
    def get_ram(self, a):
        return self.ram[a - self.ram_min_address]
    
    def set_ram(self, a, v):
        self.ram[a - self.ram_min_address] = v & 0xFF
    
    def get_sreg(self, bit):
        return getattr(self, 'flag_' + self.flag_names[bit])
    
    def set_sreg(self, bit, v):
        setattr(self, 'flag_' + self.flag_names[bit], v)
    
    def dest4_const(self, w):
        v = (w & 0xF) | ((w >> 4) & 0xF0)
        r = 16 + ((w >> 4) & 0x0F)
        return (r, v)
    
    def dest5_src5(self, w):
        d = (w >> 4) & 0x1F
        r = ((w >> 5) & 0x10) | (w & 0xF)
        return (d, r)
    
    def code7_reg5(self, w):
        r = (w >> 4) & 0x1F
        c = ((w >> 5) & 0x70) | (w & 0xF)
        return (c, r)
    
    def code5_const7(self, w):
        k = (w >> 3) & 0x7F
        c = ((w >> 7) & 0x18) | (w & 0x7)
        return (c, k)
    
    def set_flags_hvc(self, a, b, c):
        a3 = (a >> 3) & 1
        b3 = (b >> 3) & 1
        nc3 = (~c >> 3) & 1
        self.flag_h = (a3 & b3) | (nc3 & a3) | (nc3 & b3)
        a7 = (a >> 7) & 1
        b7 = (b >> 7) & 1
        nc7 = (~c >> 7) & 1
        self.flag_v = 1 if a7 == b7 == nc7 else 0
        self.flag_c = (a7 & b7) | (nc7 & a7) | (nc7 & b7)
    
    def set_flags_nsz(self, r):
        self.set_flags_ns(r)
        self.flag_z = r == 0
    
    def set_flags_ns(self, r):
        self.flag_n = (r >> 7) & 1
        self.flag_s = self.flag_v ^ self.flag_n
    
    def set_flags_bitwise(self, r):
        self.flag_v = 0
        self.set_flags_nsz(r)
    
    def instruction_size(self, w):
        return 2 if (w & 0xFC0F == 0x9000) or (w & 0xFE0C == 0x940C) else 1
    
    def not_implemented(self, w):
        raise Exception("Not implemented instruction %04X" % w)

class Peripherals(object):
    
    def __init__(self, executor):
        self.executor = executor
    
    def write(self, port, value):
        if port == 0x0C:
            self.io_udr(value)
        elif port == 0x3D:
            self.io_spl(value)
        elif port == 0x3E:
            self.io_sph(value)
        else:
            raise ValueError('Unsupported IO register for OUT: ' + str(port))
    
    def read(self, port):
        if port == 0x0C:
            return self.io_udr()
        elif port == 0x3D:
            return self.io_spl()
        elif port == 0x3E:
            return self.io_sph()
        elif port == 0x3F:
            return self.io_sreg()
        else:
            raise ValueError('Unsupported IO register for IN: ' + str(port))
    
    def io_udr(self, value = None):
        if value != None:
            sys.stdout.write(chr(value))
        else:
            ch = sys.stdin.read(1)
            return ord(ch) if len(ch) > 0 else 0
    
    def io_spl(self, value = None):
        ex = self.executor
        if value != None:
            ex.sp = (ex.sp & 0xFF00) | value
        else:
            return ex.sp & 0xFF
    
    def io_sph(self, value = None):
        ex = self.executor
        if value != None:
            ex.sp = (ex.sp & 0xFF) | (value << 8)
        else:
            return (ex.sp >> 8) & 0xFF
    
    def io_sreg(self):
        ex = self.executor
        res = ex.flag_c
        res |= ex.flag_z << 1
        res |= ex.flag_n << 2
        res |= ex.flag_v << 3
        res |= ex.flag_s << 4
        res |= ex.flag_h << 5
        res |= ex.flag_t << 6
        res |= ex.flag_i << 7
        return res
    

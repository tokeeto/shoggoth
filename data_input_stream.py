import struct


class ObjectStreamReader(object):
    def __init__(self, s):
        self.stream = s
        self.stream.read(2 + 2)
        self.cur_block_remaining = self.get_block_length()

    def get_block_length(self):
        type = ord(self.stream.read(1))
        if type == 0x7a:
            return struct.unpack('>i', self.stream.read(4))[0]
        elif type == 0x77:
            return ord(self.stream.read(1)[0])
        else:
            print("hmm")

    def read(self, num):
        if num <= self.cur_block_remaining:
            self.cur_block_remaining -= num
            return self.stream.read(num)
        else:
            if self.cur_block_remaining != 0:
                print("huh")
            else:
                self.cur_block_remaining = self.get_block_length()
                return self.read(num)

    def read_float(self):
        l = 4
        d = self.read(l)
        return struct.unpack('>f', d)[0]

    def read_int(self):
        l = 4
        d = self.read(l)
        return struct.unpack('>i', d)[0]

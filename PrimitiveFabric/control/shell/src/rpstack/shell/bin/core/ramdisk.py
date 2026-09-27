from rpstack.shell.support import split_arguments
'''
Created by Valentin Solina, Part of mipyshell project
Dinamically allocating RAM backed FAT file system for MicroPython
'''

import uos
from rpstack.shell.support import vfses as _vfses

class RAMDynBlockDev:
    # Prepare a block table whose byte buffers are allocated only when written.
    def __init__(self, block_size, num_blocks):
        self.block_size = block_size
        self.data = [None for a in range(num_blocks)]

    # Read allocated RAM blocks and supply zero bytes for unallocated blocks.
    def readblocks(self, block_num, buf):
        for bn in range(len(buf) // self.block_size):
            if self.data[block_num + bn] is not None:
                block = self.data[block_num + bn]
                for i in range(self.block_size):
                    buf[bn + i] = block[i]
            else:
                for i in range(self.block_size):
                    buf[bn + i] = 0

    # Allocate RAM blocks on demand and copy incoming block data into them.
    def writeblocks(self, block_num, buf):
        for bn in range(len(buf) // self.block_size):
            if self.data[block_num + bn] is None:
                self.data[block_num + bn] = bytearray(self.block_size)
            block = self.data[block_num + bn]
            for i in range(self.block_size):
                block[i] = buf[bn + i]

    # Handle synchronization and expose block count/size to the virtual filesystem.
    def ioctl(self, op, arg):
        if op == 3: # sync
            self.cleanup()
        if op == 4: # get number of blocks
            return len(self.data)
        if op == 5: # get block size
            return self.block_size

    # Release buffers for blocks containing only zero bytes.
    def cleanup(self):
        idx = 0
        for block in self.data:
            if block is not None:
                skip = False
                for i in range(self.block_size):
                    if block[i] != 0:
                        skip = True
                        continue
                if not skip:
                    print ("RAMfs dealloc {}".format(idx))
                    self.data[idx] = None
            idx += 1

    # Print a diagnostic when the RAM block device is finalized.
    def __del__(self):
        print ("Called RAMdisk deallocator")


# Parse RAM-disk geometry, format a FAT filesystem, and mount it at the requested path.
def run(context, arguments):
    args = split_arguments(arguments)
    if len(args) < 1:
        print ("Usage:")
        print ("ramdisk <path> count block_size")
        print ("eg. ramdisk /ram0 50 512")
        print ("    mounts 25KB ramdisk to /ram0")
        return

    pth = args[0]
    bsize = 512
    cnt = 50
    if len(args) > 1:
        cnt = int(args[1])
    if len(args) > 2:
        bsize = int(args[2])
    if bsize * cnt < 512*50:
        print ("Min disk size is {}KB".format(512*50/1024))
        print ("Entered {}KB".format(bsize*cnt/1024))
        return

    print ("Creating filesystem of {}KB in {}".format(bsize*cnt/1024, pth))
    bdev = RAMDynBlockDev(bsize, cnt)
    uos.VfsFat.mkfs(bdev)
    vfs = uos.VfsFat(bdev)
    uos.mount(vfs, pth)
    _vfses[pth] = (vfs, bdev)

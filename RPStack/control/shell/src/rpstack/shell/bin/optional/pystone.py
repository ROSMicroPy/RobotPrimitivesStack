from rpstack.shell.support import split_arguments
FOREGROUND_ONLY = True

# Slightly adjusted standard pystone

"""
"PYSTONE" Benchmark Program
Version:        Python/1.2 (corresponds to C/1.1 plus 3 Pystone fixes)
Author:         Reinhold P. Weicker,  CACM Vol 27, No 10, 10/84 pg. 1013.
                Translated from ADA to C by Rick Richardson.
                Every method to preserve ADA-likeness has been used,
                at the expense of C-ness.
                Translated from C to Python by Guido van Rossum.
Version History:
                Version 1.1 corrects two bugs in version 1.0:
                First, it leaked memory: in Proc1(), NextRecord ends
                up having a pointer to itself.  I have corrected this
                by zapping NextRecord.PtrComp at the end of Proc1().
                Second, Proc3() used the operator != to compare a
                record to None.  This is rather inefficient and not
                true to the intention of the original benchmark (where
                a pointer comparison to None is intended; the !=
                operator attempts to find a method __cmp__ to do value
                comparison of the record).  Version 1.1 runs 5-10
                percent faster than version 1.0, so benchmark figures
                of different versions can't be compared directly.
                Version 1.2 changes the division to floor division.
                Under Python 3 version 1.1 would use the normal division
                operator, resulting in some of the operations mistakenly
                yielding floats. Version 1.2 instead uses floor division
                making the benchmark a integer benchmark again.
"""

LOOPS = 50000

from utime import ticks_ms


__version__ = "1.2"


# Expose the device millisecond timer as seconds for benchmark timing.
def clock():
    return ticks_ms()/1000

[Ident1, Ident2, Ident3, Ident4, Ident5] = range(1, 6)

class Record:

    # Create the linked-record fields exercised by the Pystone benchmark.
    def __init__(self, PtrComp = None, Discr = 0, EnumComp = 0,
                       IntComp = 0, StringComp = 0):
        self.PtrComp = PtrComp
        self.Discr = Discr
        self.EnumComp = EnumComp
        self.IntComp = IntComp
        self.StringComp = StringComp

    # Make a shallow copy of benchmark record fields.
    def copy(self):
        return Record(self.PtrComp, self.Discr, self.EnumComp,
                      self.IntComp, self.StringComp)

TRUE = 1
FALSE = 0

# Run the benchmark and print elapsed time and iterations per second.
def main(loops=LOOPS):
    benchtime, stones = pystones(loops)
    print("Pystone(%s) time for %d passes = %g" % \
          (__version__, loops, benchtime))
    print("This machine benchmarks at %g pystones/second" % stones)

# Return benchmark timing and throughput from the main measurement routine.
def pystones(loops=LOOPS):
    return Proc0(loops)

IntGlob = 0
BoolGlob = FALSE
Char1Glob = '\0'
Char2Glob = '\0'
Array1Glob = [0]*51
Array2Glob = [x[:] for x in [Array1Glob]*51]
PtrGlb = None
PtrGlbNext = None

# Initialize benchmark state and time the standard mix of record, array, arithmetic, and branch
# work.
def Proc0(loops=LOOPS):
    global IntGlob
    global BoolGlob
    global Char1Glob
    global Char2Glob
    global Array1Glob
    global Array2Glob
    global PtrGlb
    global PtrGlbNext

    starttime = clock()
    for i in range(loops):
        pass
    nulltime = clock() - starttime

    PtrGlbNext = Record()
    PtrGlb = Record()
    PtrGlb.PtrComp = PtrGlbNext
    PtrGlb.Discr = Ident1
    PtrGlb.EnumComp = Ident3
    PtrGlb.IntComp = 40
    PtrGlb.StringComp = "DHRYSTONE PROGRAM, SOME STRING"
    String1Loc = "DHRYSTONE PROGRAM, 1'ST STRING"
    Array2Glob[8][7] = 10

    starttime = clock()

    for i in range(loops):
        Proc5()
        Proc4()
        IntLoc1 = 2
        IntLoc2 = 3
        String2Loc = "DHRYSTONE PROGRAM, 2'ND STRING"
        EnumLoc = Ident2
        BoolGlob = not Func2(String1Loc, String2Loc)
        while IntLoc1 < IntLoc2:
            IntLoc3 = 5 * IntLoc1 - IntLoc2
            IntLoc3 = Proc7(IntLoc1, IntLoc2)
            IntLoc1 = IntLoc1 + 1
        Proc8(Array1Glob, Array2Glob, IntLoc1, IntLoc3)
        PtrGlb = Proc1(PtrGlb)
        CharIndex = 'A'
        while CharIndex <= Char2Glob:
            if EnumLoc == Func1(CharIndex, 'C'):
                EnumLoc = Proc6(Ident1)
            CharIndex = chr(ord(CharIndex)+1)
        IntLoc3 = IntLoc2 * IntLoc1
        IntLoc2 = IntLoc3 // IntLoc1
        IntLoc2 = 7 * (IntLoc3 - IntLoc2) - IntLoc1
        IntLoc1 = Proc2(IntLoc1)

    benchtime = clock() - starttime - nulltime
    if benchtime == 0.0:
        loopsPerBenchtime = 0.0
    else:
        loopsPerBenchtime = (loops / benchtime)
    return benchtime, loopsPerBenchtime

# Exercise linked-record copies, field mutation, and enumeration branches in the benchmark.
def Proc1(PtrParIn):
    PtrParIn.PtrComp = NextRecord = PtrGlb.copy()
    PtrParIn.IntComp = 5
    NextRecord.IntComp = PtrParIn.IntComp
    NextRecord.PtrComp = PtrParIn.PtrComp
    NextRecord.PtrComp = Proc3(NextRecord.PtrComp)
    if NextRecord.Discr == Ident1:
        NextRecord.IntComp = 6
        NextRecord.EnumComp = Proc6(PtrParIn.EnumComp)
        NextRecord.PtrComp = PtrGlb.PtrComp
        NextRecord.IntComp = Proc7(NextRecord.IntComp, 10)
    else:
        PtrParIn = NextRecord.copy()
    NextRecord.PtrComp = None
    return PtrParIn

# Exercise integer adjustment and a character-controlled loop using benchmark globals.
def Proc2(IntParIO):
    IntLoc = IntParIO + 10
    while 1:
        if Char1Glob == 'A':
            IntLoc = IntLoc - 1
            IntParIO = IntLoc - IntGlob
            EnumLoc = Ident1
        if EnumLoc == Ident1:
            break
    return IntParIO

# Exercise pointer selection and update the global record's integer field.
def Proc3(PtrParOut):
    global IntGlob

    if PtrGlb is not None:
        PtrParOut = PtrGlb.PtrComp
    else:
        IntGlob = 100
    PtrGlb.IntComp = Proc7(10, IntGlob)
    return PtrParOut

# Exercise boolean expressions and set the benchmark's second global character.
def Proc4():
    global Char2Glob

    BoolLoc = Char1Glob == 'A'
    BoolLoc = BoolLoc or BoolGlob
    Char2Glob = 'B'

# Reset the benchmark's first character and boolean flag for an iteration.
def Proc5():
    global Char1Glob
    global BoolGlob

    Char1Glob = 'A'
    BoolGlob = FALSE

# Exercise enumeration dispatch with a branch dependent on the global integer.
def Proc6(EnumParIn):
    EnumParOut = EnumParIn
    if not Func3(EnumParIn):
        EnumParOut = Ident4
    if EnumParIn == Ident1:
        EnumParOut = Ident1
    elif EnumParIn == Ident2:
        if IntGlob > 100:
            EnumParOut = Ident1
        else:
            EnumParOut = Ident4
    elif EnumParIn == Ident3:
        EnumParOut = Ident2
    elif EnumParIn == Ident4:
        pass
    elif EnumParIn == Ident5:
        EnumParOut = Ident3
    return EnumParOut

# Exercise the benchmark's small integer arithmetic helper.
def Proc7(IntParI1, IntParI2):
    IntLoc = IntParI1 + 2
    IntParOut = IntParI2 + IntLoc
    return IntParOut

# Exercise indexed one- and two-dimensional array updates and reset the global integer.
def Proc8(Array1Par, Array2Par, IntParI1, IntParI2):
    global IntGlob

    IntLoc = IntParI1 + 5
    Array1Par[IntLoc] = IntParI2
    Array1Par[IntLoc+1] = Array1Par[IntLoc]
    Array1Par[IntLoc+30] = IntLoc
    for IntIndex in range(IntLoc, IntLoc+2):
        Array2Par[IntLoc][IntIndex] = IntLoc
    Array2Par[IntLoc][IntLoc-1] = Array2Par[IntLoc][IntLoc-1] + 1
    Array2Par[IntLoc+20][IntLoc] = Array1Par[IntLoc]
    IntGlob = 5

# Compare two characters and return the corresponding benchmark enumeration.
def Func1(CharPar1, CharPar2):
    CharLoc1 = CharPar1
    CharLoc2 = CharLoc1
    if CharLoc2 != CharPar2:
        return Ident1
    else:
        return Ident2

# Exercise indexed character tests and lexicographic string comparison.
def Func2(StrParI1, StrParI2):
    IntLoc = 1
    while IntLoc <= 1:
        if Func1(StrParI1[IntLoc], StrParI2[IntLoc+1]) == Ident1:
            CharLoc = 'A'
            IntLoc = IntLoc + 1
    if CharLoc >= 'W' and CharLoc <= 'Z':
        IntLoc = 7
    if CharLoc == 'X':
        return TRUE
    else:
        if StrParI1 > StrParI2:
            IntLoc = IntLoc + 7
            return TRUE
        else:
            return FALSE

# Test whether the enumeration equals the benchmark's third identifier.
def Func3(EnumParIn):
    EnumLoc = EnumParIn
    if EnumLoc == Ident3: return TRUE
    return FALSE

# Parse the requested iteration count and launch the Pystone benchmark.
def run(context, arguments):
    args = split_arguments(arguments)
    import sys
    # Print benchmark argument usage and exit with the command's error status.
    def error(msg):
        print(msg, end=' ', file=sys.stderr)
        print("usage: %s [number_of_loops]" % 'pystone', file=sys.stderr)
        sys.exit(100)
    nargs = len(args)
    if nargs > 1:
        error("%d arguments are too many;" % nargs)
    elif nargs == 1:
        try: loops = int(args[0])
        except ValueError:
            error("Invalid argument %r;" % args[0])
    else:
        loops = LOOPS
    main(loops)

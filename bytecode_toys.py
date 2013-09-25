# Copyright (c) 2013 by Pat Miller
# This work is made available under the terms of the Creative Commons
# Attribution-ShareAlike 3.0 license, http://creativecommons.org/licenses/by-sa/3.0/
#
# I'm fine with any use of this, commercial or otherwise.  Give me
# credit though!
#
#
# Pat Miller -- patrick.miller@gmail.com

"""bytecode_toys
This work is made available under the terms of the Creative Commons
Attribution-ShareAlike 3.0 license, http://creativecommons.org/licenses/by-sa/3.0/

Some simple (but powerful!) toys to illustrate how to use bytecodes
for fun and profit!

This is guilt-ware.

If you think this code saves you money (remember, time is money!),
I will happily take PayPal donations to cover beer, pizza,
my kids' college tuition, or a small airplane (please specify).

Don't use this in mission critical software without enough
testing to make sure you think it's safe.  This depends on
some possibly fragile assumptions, so it can give you unexpected
results. YMMV.

User assumes all risk.

I'm fine with any use of this, commercial or otherwise.  Give me
credit though!

Pat Miller -- patrick.miller@gmail.com

"""

__version__ = (0,1)


def __transform_codeobjects__(co,f):
    "In this helper, we apply a transform across nested function defs"
    # Only transform code objects
    from types import CodeType
    if not isinstance(co,CodeType): return co

    # First, transform all the underlying code objects
    constants = tuple( __transform_codeobjects__(k,f)
                       for k in co.co_consts )

    # co.co_consts is read-only, we must rebuild a new code obj
    co = CodeType(
        co.co_argcount,
        co.co_nlocals,
        co.co_stacksize,
        co.co_flags,
        co.co_code,
        constants,
        co.co_names,
        co.co_varnames,
        co.co_filename,
        co.co_name,
        co.co_firstlineno,
        co.co_lnotab,
        co.co_freevars,
        co.co_cellvars)
    return f(co)

def __pc_to_byteplay_offset__(codelist):
    "byteplay offsets do not correspond to actual bytecode offsets"
    from byteplay import SetLineno,hasarg,Label
    result = {}
    pc = 0
    for offset,(opcode,_) in enumerate(codelist):
        if pc not in result:
            result[pc] = offset
        if opcode == SetLineno or isinstance(opcode,Label):
            pass
        elif opcode in hasarg:
            pc += 3
        else:
            pc += 1
    return result

class LittleTimer:
    """A timer to use with a with block.

    This small timer class that has very low overhead to reduce
    the error bars associated with typical loop strategies.

    It works by building a custom function with n copies of
    the with body in it.  It slaps on start/stop timers and
    does the simple math. It avoids loop overhead by actually
    unrolling the implied loop.  This can get large!

    with LittleTimer(1000) as T:
        a = b*c
    print T.rate,'+/-',T.rate_errorbar,'per second'
    print T.time,'+/-',T.time_errorbar,'each instance'

    The above is vastly more reliable than
    t0 = time.time()
    for i in xrange(10):
        a = b*c
    t = time.time()-t0

    and doesn't restrict you to a one-liner string for evaluation
    
    e.g. timer.Timer('a = b*c').timeit(10)
    """
    
    __tick = 1e-6
    @property
    def tick(self):
        "Assumed tick size of timer -- default 1 microsecond"
        return self.__tick
    @tick.setter
    def __set_tick(self,tick):
        self.__tick = tick
        return

    def __init__(self,n=10):
        "__init__(n) - n is the number of replications of the body"
        self.__n = n
        self.__once = 0.0
        self.__locals = {}
        self.__globals = {}
        self.__bytecodes = []
        self.__line = 0
        self.__code = None
        self.__oneshot = False
        return

    def __enter__(self):
        """With block entry

        On entry to the with, we grab the byte codes that make
        up just the body of the block.  We also get a copy of
        all the local values take participate in the body.

        On block exit (or if we call the timer() function),
        we'll build a custom function from these parts and
        run it to get the time.

        We are expecting to be called in the form:
        with LittleTimer() as T:
           block

        which looks like:
             blah blah blah
             CALL_FUNCTION x
             SETUP_WITH
             <something to store it or a pop_top>
             code body
             POP_BLOCK
             LOAD_CONST None
             WITH_CLEANUP

        We don't support anything other than storing to a
        variable or not storing at all
        """
        # We pull in some useful bits
        import inspect
        from byteplay import Code,haslocal,SetLineno, \
            SETUP_WITH,WITH_CLEANUP,\
            STORE_FAST,STORE_NAME,STORE_GLOBAL,\
            POP_TOP,POP_BLOCK

        frame = inspect.currentframe(1)
        self.__code = code = Code.from_code(frame.f_code)
        self.__line = frame.f_lineno
        self.__globals = frame.f_globals

        # The SetLineno instructions get in the way here
        # since I want to find the actual instruction
        # by offset.  I'll just strip them out
        instructions = code.code
        nolines = [x for x in instructions if x[0] != SetLineno]
        instructions[:] = nolines
        pc = __pc_to_byteplay_offset__(instructions).get(frame.f_lasti)
        assert pc is not None,"Found invalid offset for with"

        # Strip off everything through the SETUP_WITH
        assert instructions[pc][0] == SETUP_WITH,"LittleTimer must be invoked from a with statement"
        end_label = instructions[pc][1]
        del instructions[:pc+1]

        # which is followed by a STORE_NAME, STORE_LOCAL,
        # STORE_GLOBAL, or POP_TOP
        assert instructions[0][0] in (\
            STORE_NAME,
            STORE_FAST,
            STORE_GLOBAL,
            POP_TOP
            ),"Only simple assignment is supported, no more complex than LittleTimer() as T"
        if instructions[0][0] == POP_TOP: self.__oneshot = True
        del instructions[0]

        # Find the closing WITH_CLEANUP
        targets = [offset for offset,(opcode,arg) in enumerate(instructions)
                   if opcode is end_label]
        assert targets,"This with-statement was not formed the way I expected"
        pc = targets[0]+1
        assert instructions[pc][0] == WITH_CLEANUP,"This with-statement was not formed the way I expected"

        # Reverse until we find a POP_BLOCK
        while pc >= 0:
            opcode = instructions[pc][0]
            if opcode == POP_BLOCK:
                break
            pc -= 1
        del instructions[pc:]
        self.__bytecodes = instructions

        # We may have some local values that we need to set up
        locals = set([x[1] for x in instructions if x[0] in haslocal])
        self.__locals = dict( (sym,frame.f_locals.get(sym,None))
                              for sym in locals )
        return self

        return self

    def __exit__(self,*args):
        "On exit, we build a timer function and run it to collect the time"
        self.timeit(self.__n)
        if self.__oneshot: print 'Rate',self.rate,'per second'
        return False

    def timeit(self,n=None):
        """Re-run the timing routine.  Returns the time for one iteration.
        
        This computes new rate, time, etc.. and resets the implied count"""
        from byteplay import \
            SetLineno, \
            LOAD_CONST,STORE_FAST,ROT_TWO, \
            CALL_FUNCTION,RETURN_VALUE, \
            BINARY_SUBTRACT, BINARY_DIVIDE
        from types import FunctionType

        # We override some of the stored information on a rerun
        if n is None:
            n = self.__n
        else:
            self.__n = n
        instructions = self.__bytecodes

        # Now we replicate the code the right number of times
        base = instructions[:]
        for i in xrange(1,self.__n):
            instructions.extend(self.__clone(base))

        # insert time.time at front and back
        # sub at end and return
        import platform,time
        if platform.system() == 'Windows':
            gettime = time.clock
        else:
            gettime = time.time
        
        instructions[0:0] = [
            (LOAD_CONST,gettime),
            (CALL_FUNCTION,0),
            ]
        instructions.extend([
            (LOAD_CONST,gettime),
            (CALL_FUNCTION,0),
            (ROT_TWO,None),
            (BINARY_SUBTRACT,None),
            (LOAD_CONST,self.__n),
            (BINARY_DIVIDE,None),
            ])

        # We may use local values in this new function
        # We add them into the body to avoid having to pass
        # them into the function with arguments
        for sym,value in self.__locals.iteritems():
            instructions[0:0] = [
                (LOAD_CONST,value),
                (STORE_FAST,sym),
                ]

        # Make it a legal function with a return and use the
        # with as the line number
        instructions.insert(0,(SetLineno,self.__line))
        instructions.append((RETURN_VALUE,None))
        
        timerbody = FunctionType(
            self.__code.to_code(),
            self.__globals,
            'timerbody')
        self.__timerbody = timerbody

        # We try to be careful with garbage collection runs
        try:
            import gc
            gc.collect()   # Do a pre-emptive collection now
            if gc.isenabled(): gc.disable()
            self.__once = timerbody()
        finally:
            gc.enable()
        return self.__once

    def __clone(self,base):
        "Used internally to clone blocks of instructions with labels"
        from byteplay import Label,CodeList
        # Pull out all the label targets
        targets = dict( (x[0],Label()) for x in base if isinstance(x[0],Label) )

        return CodeList(
            (targets.get(x[0],x[0]),
                   targets.get(x[1],x[1]))
            for x in base)

    @property
    def rate(self):
        "approximate number of executions per second"
        try:
            return 1.0/self.__once
        except ZeroDivisionError:
            return 0

    @property
    def rate_errorbar(self):
        "a bound on the rate accuracy based on clock granularity"
        time_for_all = self.__once*self.__n
        # Each clock can be off a tick, about 1 microsecond
        bar_time = time_for_all + 2*self.tick
        try:
            bar_once = bar_time / self.__n
            bar_rate = 1.0/bar_once
        except ZeroDivisionError:
            return 0
        return self.rate - bar_rate

    @property
    def time(self):
        "time for one execution in seconds"
        return self.__once

    @property
    def time_errorbar(self):
        "a bound on the time accuracy based on clock granularity"
        try:
            return 2*self.tick/self.__n
        except ZeroDivisionError:
            return 2*self.tick


def __cache_globals__(co,func_globals):
    "Cache global objects in co_consts.  See @cache_globals.  Returns code object"
    from byteplay import Code, LOAD_CONST, LOAD_GLOBAL, LOAD_ATTR
    # First, we want to crack open the function and look at it's bytecodes
    code = Code.from_code(co)

    # Look at each load global and replace with a load const if the
    # global value is currently available.  At the same time, if we
    # find something like <const>.attr (and the attr is available),
    # we keep folding
    missing = object()
    pc = 0
    while pc < len(code.code):
        op,arg = code.code[pc]
        if op == LOAD_GLOBAL:
            const = func_globals.get(arg,missing)
            if const is not missing:
                code.code[pc] = (LOAD_CONST,const)
            else:
                const = __builtins__.get(arg,missing)
                if const is not missing:
                    code.code[pc] = (LOAD_CONST,const)

        elif op == LOAD_ATTR:
            prev_op,prev_arg = code.code[pc-1]
            const = getattr(prev_arg,arg,missing)
            if const is not missing:
                code.code[pc-1:pc+1] = [(LOAD_CONST,const)]
                pc -= 1
        pc += 1

    return code.to_code()

def cache_globals(f):
    """This decorator will fold global references into local constants

    The idea is that something like math.sin takes two global dictionary
    lookups.  While we can improve that somewhat with careful imports,
    we can't fully remove the impact.  Even in something as simple as

    def g(x): ...
    def f(y): return g(y*2)

    The call to g() requires a global lookup... We know this will never
    change (It is possible, of course, with monkey patching or very clever
    code), but we suffer the lookup every time.   This decorator looks each
    global up once (at decoration time) and caches it as a special local
    constant."""
    def action(co):
        return __cache_globals__(co,f.func_globals)
    f.func_code = __transform_codeobjects__(f.func_code,action)
    return f


def __smartdebug__(co,func_globals):
    """Apply smartdebug to code objects, see @smartdebug"""

    from byteplay import Code,SetLineno,Label,LOAD_GLOBAL,POP_JUMP_IF_FALSE,POP_JUMP_IF_TRUE,JUMP_FORWARD
    code = Code.from_code(co)
    instructions = code.code

    # First, find all the "if DEBUG:" and "if not DEBUG"
    # We collect in reverse order so that we can update
    # in place more easily
    debugs = []
    for offset,op_arg in enumerate(instructions):
        if op_arg == (LOAD_GLOBAL,'DEBUG') and instructions[offset+1][0] in (POP_JUMP_IF_FALSE,POP_JUMP_IF_TRUE):
            debugs.insert(0,offset)

    # We want the bounds of the DEBUG true part and DEBUG false part for each
    # most ifs look like
    # LOAD_GLOBAL DEBUG
    # POP_JUMP_IF_FALSE L1  (sense may be reversed with _TRUE)
    #   ...
    # JUMP_FORWARD L2
    # L1:
    #   ...
    # L2:
    # They look different at the ends of loops, but I'm skipping those
    def back_one(x):
        while x > 0:
            opcode = instructions[x][0]
            if opcode != SetLineno and not isinstance(opcode,Label):
                break
            x -= 1
        return x
    def offset_of(L):
        for off,(op,_) in enumerate(instructions):
            if op is L: return off
        return None
    def true_false(x):
        pop_jump,L1 = instructions[x+1]
        O1 = offset_of(L1)
        if O1 < x: return None  # Jumping backward, Loop if
        OJF = back_one(O1)
        jf,L2 = instructions[OJF]
        if jf != JUMP_FORWARD: return None # Not my pattern
        O2 = offset_of(L2)
        if pop_jump == POP_JUMP_IF_FALSE:
            return ((x+2,OJF),(OJF+1,O2),(x,O2))
        return ((OJF+1,O2),(x+2,OJF),(x,O2))
        

    while debugs:
        x = debugs[0]
        del debugs[0]
        bounds = true_false(x)
        if not bounds: continue
        (t0,t1),(f0,f1),(a,b) = bounds
        if func_globals.get('DEBUG',False):
            using = instructions[t0:t1]
        else:
            using = instructions[f0:f1]
        instructions[a:b] = using

    return code.to_code()

def smartdebug(f):
    """a decorator to intelligently remove if DEBUG: code

    We often spend a lot of time sprinkling debug code around
    our functions.  We sometimes want it turned on, and more
    often turned off.  This decorator checks the global DEBUG
    statement once, and then strips out conditional code as
    needed.
    """
    def action(co):
        return __smartdebug__(co,f.func_globals)
    f.func_code = __transform_codeobjects__(f.func_code,action)
    return f

def __levels__(instructions):
    "find implied stack levels for each bytecode.  Not general purpose"
    from byteplay import getse
    levels = []
    level = 0
    for pc,(op,arg) in enumerate(instructions):
        try:
            pop,push = getse(op,arg)
        except ValueError:
            pop = 0
            push = 0
        level += (push-pop)
        levels.append(level)
    return levels

def __unprint__(co):
    "Apply unprint to code objects.  See @unprint"
    from byteplay import Code,getse, \
        PRINT_ITEM,PRINT_NEWLINE, \
        PRINT_ITEM_TO, PRINT_NEWLINE_TO, \
        POP_TOP, ROT_TWO, DUP_TOP

    code = Code.from_code(co)
    instructions = code.code

    # Now we kill every PRINT_NEWLINE and PRINT_ITEM
    # (and associated value computations)
    levels = __levels__(instructions)
    kills = set()

    def killback(pc):
        kills.add(pc)
        target_level = levels[pc]
        pc -= 1
        while pc >= 0 and levels[pc] > target_level:
            kills.add(pc)
            pc -= 1
        return pc
    for pc,(op,arg) in enumerate(instructions):
        if pc in kills: continue

        if op == PRINT_NEWLINE:
            kills.add(pc)
        elif op == PRINT_ITEM:
            pc = killback(pc)
        elif op == PRINT_ITEM_TO:
            pc2 = killback(pc)    # Kill the expression to print
            pc3 = killback(pc2)   # Kill the expression for out

            # This chain of PRINT_ITEM_TO ends in one of
            # two ways... with a PRINT_ITEM_TO/POP_TOP
            # or a PRINT_ITEM_TO/PRINT_NEWLINE_TO
            pc_end = pc
            while pc_end < len(instructions):
                if instructions[pc_end] == (PRINT_ITEM_TO,None):
                    if instructions[pc_end+1][0] in (POP_TOP,PRINT_NEWLINE_TO):
                        pc_end += 2
                        break
                pc_end += 1
            for i in xrange(pc,pc_end): kills.add(i)
            
        elif op == PRINT_NEWLINE_TO:
            # You get this if you just have print >>out
            killback(pc)

    for x in reversed(sorted(kills)):
        del instructions[x]
    
    return code.to_code()

def unprint(f):
    """A decorator to remove print statements

    Strips out all print statements (and any side effects involved
    in their output)."""
    
    f.func_code = __transform_codeobjects__(f.func_code,__unprint__)
    return f

def __debuggable__(co):
    "Apply DEBUG() calls in a code object.  See @debuggable"
    from byteplay import Code, LOAD_GLOBAL, CALL_FUNCTION, POP_TOP
    # First, we want to crack open the function and look at it's bytecodes
    code = Code.from_code(co)
    pc = 0
    while pc < len(code.code):
        # Look for LOAD_GLOBAL,DEBUG
        op,arg = code.code[pc]
        if op != LOAD_GLOBAL or arg != 'DEBUG':
            pc += 1
            continue
        expr_start = pc
        pc += 1

        # Figure out the "stack level" at each opcode
        levels = __levels__(code.code)
        start_level = levels[expr_start]

        # Walk forward seeking a CALL_FUNCTION at the same level
        n = start_level
        for n in range(pc+1,len(code.code)):
            if levels[n] == start_level: break

        # We should be at a CALL_FUNCTION.  It's value should
        # not be used.  If it is, we don't remove it
        if code.code[n][0] != CALL_FUNCTION: continue
        if code.code[n+1][0] != POP_TOP: continue
        del code.code[expr_start:n+2]

    return code.to_code()

def debuggable(f):
    """A decorator to remove DEBUG() calls when DEBUGGING is False

    Finds any call to a function called DEBUG() unless there is a
    variable in the function's global space called DEBUGGING that
    evaluates to True"""
    
    debugging = f.func_globals.get("DEBUGGING",False)
    if debugging: return f

    f.func_code = __transform_codeobjects__(f.func_code,__debuggable__)
    return f

def make_local_functions_constant():
    """A mass code object rewriter

    The idea here is that you often write functions that call other
    functions from the same module.  It would be *much* better if
    we didn't have to do a full blown global dictionary lookup just
    to get the function that is sitting right next door to us.

    This is only for top-level functions, but it possible to extend
    to methods and nested functions.
    """

    import inspect
    from types import FunctionType

    frame = inspect.currentframe(1)
    local_functions = {}
    for sym,value in frame.f_globals.iteritems():
        if isinstance(value,FunctionType) and value.func_globals is frame.f_globals:
            local_functions[sym] = value

    __mass_replace__(local_functions.values(),local_functions)
    return

def make_local_modules_constant():
    """A mass code object rewriter

    The idea here is that when you import a module and then
    use it throughout your code, you really don't want to
    have to pay a dictionary lookup because that value will
    not change even if its contents may:  E.g.

    import math

    def foo(x):
        # Math is never going to change once imported
        return math.sin(x)+1
    """
    import inspect
    from types import FunctionType,ModuleType

    frame = inspect.currentframe(1)
    local_functions = []
    local_modules = {}
    for sym,value in frame.f_globals.iteritems():
        if isinstance(value,FunctionType) and value.func_globals is frame.f_globals:
            local_functions.append(value)
        elif isinstance(value,ModuleType):
            local_modules[sym] = value

    __mass_replace__(local_functions,local_modules)
    return

def __mass_replace__(functions,what):
    "Mass replace the global from what in the functions"
    def transform(co):
        from byteplay import Code, LOAD_CONST, LOAD_GLOBAL
        code = Code.from_code(co)
        newcode = []
        for pc,(op,arg) in enumerate(code.code):
            if op == LOAD_GLOBAL and arg in what:
                code.code[pc] = (LOAD_CONST,what[arg])
        return code.to_code()

    for value in functions:
        value.func_code = __transform_codeobjects__(value.func_code,transform)

    return


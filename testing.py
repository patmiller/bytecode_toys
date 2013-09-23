import unittest
import math

DEBUG = False

class TestToys(unittest.TestCase):
    def test_import(self):
        import bytecode_toys
        
        # The decorators should exist
        bytecode_toys.unprint
        bytecode_toys.smartdebug
        bytecode_toys.cache_globals

        # The bytecode based timer should exist
        bytecode_toys.LittleTimer
        return

    def test_unprint(self):
        from bytecode_toys import unprint
        import sys,StringIO
        @unprint
        def f(x):
            print x
            print 'hello, world!',
            return
        save = sys.stdout
        out = StringIO.StringIO()
        try:
            sys.stdout = out
            f(10)
        finally:
            sys.stdout = save
        out.seek(0)
        self.assertEquals(out.read(),'')
        return

    def test_smartdebug(self):
        from bytecode_toys import smartdebug
        global DEBUG

        DEBUG = True
        @smartdebug
        def f(x):
            if DEBUG:
                x = 10
            return x

        DEBUG = False
        @smartdebug
        def g(x):
            if DEBUG:
                x = 10
            return x
        self.assertEquals(f(0),10)
        self.assertEquals(g(0),0)
        return

    def test_cache_globals(self):
        from bytecode_toys import cache_globals
    
        @cache_globals
        def f(x):
            return math.sin(x) + math.pi

        self.assertTrue( math.sin in f.func_code.co_consts )
        self.assertTrue( math.pi in f.func_code.co_consts )
        self.assertFalse( 'math' in f.func_code.co_names )
        self.assertFalse( 'sin' in f.func_code.co_names )
        self.assertFalse( 'pi' in f.func_code.co_names )


        def g(x):
            return math.sin(x) + math.pi
        self.assertFalse( math.sin in g.func_code.co_consts )
        self.assertFalse( math.pi in g.func_code.co_consts )
        self.assertTrue( 'math' in g.func_code.co_names )
        self.assertTrue( 'sin' in g.func_code.co_names )
        self.assertTrue( 'pi' in g.func_code.co_names )

        return


if __name__ == '__main__':
    unittest.main()


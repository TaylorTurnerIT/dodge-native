"""Descriptor authentication only: real class definitions, never learner instances."""
import ast
import importlib.util
import inspect
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import torch

import contracts as c
import driver_binding as binding
import runtime_adapter as adapter
from successor import curriculum


TEACHER = c.HERE/'runtime/dodge_rl/models/teacher.py'
STATIC_METHODS = ('_initialize_head','_validate_inputs')


class ClassAuthenticationTests(unittest.TestCase):
    def teacher(self):
        # Load the entire unchanged module under a test-only name. No package
        # __init__, native extension, constructor, method body or restore runs.
        self.assertEqual(c.sha(TEACHER),
                         'e4d7f597a2824c2b0d4ba261dddc9d7d1ee1d5592c2fc966a44c54b5ec417e35')
        name = '_class_auth_real_teacher_fixture'
        spec = importlib.util.spec_from_file_location(name,TEACHER)
        module = importlib.util.module_from_spec(spec)
        self.enterContext(patch.dict(sys.modules,{name:module}))
        with patch.object(torch.nn.Module,'__init__',side_effect=AssertionError('model construction forbidden')) as construct, \
             patch.object(torch,'load',side_effect=AssertionError('checkpoint load forbidden')) as load:
            spec.loader.exec_module(module)
        self.assertEqual(construct.call_count,0)
        self.assertEqual(load.call_count,0)
        self.assertFalse(any(name == 'dodge_rl' or name.startswith('dodge_rl.') for name in sys.modules))
        return module

    def property_module(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        path = Path(directory)/'property_fixture.py'
        path.write_text('class PropertyFixture:\n'
                        '    @property\n'
                        '    def value(self):\n'
                        '        raise AssertionError("property must not execute")\n')
        name = '_class_auth_property_fixture'
        module = types.ModuleType(name)
        module.__file__ = str(path)
        self.enterContext(patch.dict(sys.modules,{name:module}))
        exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
        return module

    def reject_teacher(self,module,member,error='descriptor differs'):
        with self.assertRaisesRegex(ValueError,error+r': OmniscientEntityTeacher\.'+member):
            adapter.authenticate_class(module,'OmniscientEntityTeacher')

    def test_unchanged_real_teacher_with_both_staticmethods(self):
        module = self.teacher()
        for name in STATIC_METHODS:
            descriptor = inspect.getattr_static(module.OmniscientEntityTeacher,name)
            self.assertIs(type(descriptor),staticmethod)
            self.assertIs(descriptor.__func__.__globals__,module.__dict__)
        adapter.authenticate_class(module,'OmniscientEntityTeacher')

    def test_unchanged_real_transformer_definition(self):
        adapter.authenticate_class(self.teacher(),'CustomTransformerLayer')

    def test_unchanged_real_curriculum_definitions_without_construction(self):
        for name in ('CurriculumAdapter','PreparedUpdates'):
            with self.subTest(name=name):
                adapter.authenticate_class(curriculum,name)

    def test_property_definition_retained_without_getter_execution(self):
        adapter.authenticate_class(self.property_module(),'PropertyFixture')

    def test_predecessor_check_reproduces_real_teacher_regression(self):
        module = self.teacher()
        path = Path(c.read(c.HERE/'input-manifest.json')['copies']['runtime_adapter.py']['source'])
        code = binding._definitions(path.read_bytes(),path,('authenticate_class',))['authenticate_class']
        original = types.FunctionType(code,dict(Path=Path,binding=binding,types=types,
                                               inspect=inspect,c=c),'authenticate_class')
        with self.assertRaisesRegex(ValueError,r'runtime class method differs: OmniscientEntityTeacher\._initialize_head'):
            original(module,'OmniscientEntityTeacher')

    def test_staticmethod_to_plain_function_rejected_for_both_members(self):
        for name in STATIC_METHODS:
            with self.subTest(name=name):
                module = self.teacher()
                cls = module.OmniscientEntityTeacher
                setattr(cls,name,inspect.getattr_static(cls,name).__func__)
                self.reject_teacher(module,name)

    def test_staticmethod_to_classmethod_rejected(self):
        for name in STATIC_METHODS:
            with self.subTest(name=name):
                module = self.teacher()
                cls = module.OmniscientEntityTeacher
                setattr(cls,name,classmethod(inspect.getattr_static(cls,name).__func__))
                self.reject_teacher(module,name)

    def test_staticmethod_to_property_rejected(self):
        module = self.teacher()
        cls = module.OmniscientEntityTeacher
        cls._initialize_head = property(inspect.getattr_static(cls,'_initialize_head').__func__)
        self.reject_teacher(module,'_initialize_head')

    def test_plain_function_to_staticmethod_rejected(self):
        module = self.teacher()
        module.OmniscientEntityTeacher.forward = staticmethod(module.OmniscientEntityTeacher.forward)
        self.reject_teacher(module,'forward')

    def test_plain_function_to_property_rejected(self):
        module = self.teacher()
        module.OmniscientEntityTeacher.forward = property(module.OmniscientEntityTeacher.forward)
        self.reject_teacher(module,'forward')

    def test_property_to_other_descriptor_kinds_rejected(self):
        for kind in (lambda value:value,staticmethod,classmethod):
            with self.subTest(kind=kind):
                module = self.property_module()
                cls = module.PropertyFixture
                cls.value = kind(inspect.getattr_static(cls,'value').fget)
                with self.assertRaisesRegex(ValueError,'descriptor differs'):
                    adapter.authenticate_class(module,'PropertyFixture')

    def test_staticmethod_subclass_rejected_without_dynamic_access(self):
        calls = []
        class DynamicStaticmethod(staticmethod):
            def __get__(self,*args):
                calls.append('get')
                raise AssertionError('dynamic staticmethod executed')
            def __getattribute__(self,name):
                calls.append(name)
                raise AssertionError('dynamic attribute executed')
        module = self.teacher()
        cls = module.OmniscientEntityTeacher
        cls._initialize_head = DynamicStaticmethod(inspect.getattr_static(cls,'_initialize_head').__func__)
        self.reject_teacher(module,'_initialize_head')
        self.assertEqual(calls,[])

    def test_property_subclass_rejected_without_dynamic_access(self):
        calls = []
        class DynamicProperty(property):
            def __get__(self,*args):
                calls.append('get')
                raise AssertionError('dynamic property executed')
            def __getattribute__(self,name):
                calls.append(name)
                raise AssertionError('dynamic attribute executed')
        module = self.property_module()
        cls = module.PropertyFixture
        cls.value = DynamicProperty(inspect.getattr_static(cls,'value').fget)
        with self.assertRaisesRegex(ValueError,'descriptor differs'):
            adapter.authenticate_class(module,'PropertyFixture')
        self.assertEqual(calls,[])

    def test_custom_descriptor_rejected_without_get(self):
        calls = []
        class DynamicDescriptor:
            def __get__(self,*args):
                calls.append('get')
                raise AssertionError('descriptor executed')
        module = self.teacher()
        module.OmniscientEntityTeacher._validate_inputs = DynamicDescriptor()
        self.reject_teacher(module,'_validate_inputs')
        self.assertEqual(calls,[])

    def test_changed_code_same_filename_and_globals_rejected(self):
        for name in (*STATIC_METHODS,'forward'):
            with self.subTest(name=name):
                module = self.teacher()
                code = compile('def '+name+'(*args,**kwargs):\n    return "changed"\n',str(TEACHER),'exec')
                body = next(value for value in code.co_consts if isinstance(value,types.CodeType))
                function = types.FunctionType(body,module.__dict__,name)
                setattr(module.OmniscientEntityTeacher,name,staticmethod(function) if name in STATIC_METHODS else function)
                self.reject_teacher(module,name,'method differs')

    def test_foreign_globals_exact_real_code_rejected(self):
        for name in (*STATIC_METHODS,'forward'):
            with self.subTest(name=name):
                module = self.teacher()
                cls = module.OmniscientEntityTeacher
                function = inspect.getattr_static(cls,name)
                if name in STATIC_METHODS:function = function.__func__
                foreign = types.FunctionType(function.__code__,dict(module.__dict__),name,function.__defaults__)
                setattr(cls,name,staticmethod(foreign) if name in STATIC_METHODS else foreign)
                self.reject_teacher(module,name,'method differs')

    def test_property_changed_code_rejected(self):
        module = self.property_module()
        path = Path(module.__file__)
        body = binding._definitions(b'def value(self):\n    return "changed"\n',path,('value',))['value']
        module.PropertyFixture.value = property(types.FunctionType(body,module.__dict__,'value'))
        with self.assertRaisesRegex(ValueError,'method differs'):
            adapter.authenticate_class(module,'PropertyFixture')

    def test_property_foreign_globals_rejected(self):
        module = self.property_module()
        function = inspect.getattr_static(module.PropertyFixture,'value').fget
        module.PropertyFixture.value = property(types.FunctionType(function.__code__,dict(module.__dict__),'value'))
        with self.assertRaisesRegex(ValueError,'method differs'):
            adapter.authenticate_class(module,'PropertyFixture')

    def test_property_injected_setter_or_deleter_rejected(self):
        for attribute in ('setter','deleter'):
            with self.subTest(attribute=attribute):
                module = self.property_module()
                descriptor = inspect.getattr_static(module.PropertyFixture,'value')
                module.PropertyFixture.value = getattr(descriptor,attribute)(lambda *args:None)
                with self.assertRaisesRegex(ValueError,'property differs'):
                    adapter.authenticate_class(module,'PropertyFixture')

    def test_foreign_class_origin_rejected(self):
        module = self.teacher()
        module.OmniscientEntityTeacher.__module__ = '_different_teacher_origin'
        with self.assertRaises((TypeError,ValueError)):
            adapter.authenticate_class(module,'OmniscientEntityTeacher')

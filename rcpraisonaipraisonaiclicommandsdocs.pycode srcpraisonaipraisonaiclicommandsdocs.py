[1mdiff --git a/src/praisonai/tests/unit/test_templates.py b/src/praisonai/tests/unit/test_templates.py[m
[1mindex d4f3a5ee..99c8c461 100644[m
[1m--- a/src/praisonai/tests/unit/test_templates.py[m
[1m+++ b/src/praisonai/tests/unit/test_templates.py[m
[36m@@ -1416,17 +1416,21 @@[m [mdef custom_search(query: str) -> str:[m
         # After context, original state should be restored[m
         # (implementation detail - registry should be isolated)[m
     [m
[32m+[m
     def test_default_custom_dirs(self):[m
         """Test that default custom tool directories are defined."""[m
         from praisonai.templates.tool_override import ToolOverrideLoader[m
[31m-        [m
[32m+[m
         loader = ToolOverrideLoader()[m
         default_dirs = loader.get_default_tool_dirs()[m
[31m-        [m
[32m+[m
         assert len(default_dirs) >= 2[m
[31m-        assert any(".praison/tools" in str(d) for d in default_dirs)[m
[31m-        assert any(".config/praison/tools" in str(d) or ".praison/tools" in str(d) for d in default_dirs)[m
[31m-    [m
[32m+[m[32m        assert any(".praison/tools" in Path(d).as_posix() for d in default_dirs)[m
[32m+[m[32m        assert any([m
[32m+[m[32m            ".config/praison/tools" in Path(d).as_posix()[m
[32m+[m[32m            or ".praison/tools" in Path(d).as_posix()[m
[32m+[m[32m            for d in default_dirs[m
[32m+[m[32m        )[m
     def test_no_scanning_on_import(self):[m
         """Test that no filesystem scanning occurs on import."""[m
         import sys[m

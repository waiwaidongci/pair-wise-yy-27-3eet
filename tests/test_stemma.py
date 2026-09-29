import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import CollationDB, DomainError

class StemmaTest(unittest.TestCase):
    def setUp(self):
        fd,self.path=tempfile.mkstemp(suffix=".db"); os.close(fd); self.db=CollationDB(self.path)
        self.owner=self.db.add_user("负责人","owner"); self.editor=self.db.add_user("编辑","editor")
        self.reviewer=self.db.add_user("审阅","reviewer"); self.outsider=self.db.add_user("外部","reviewer")
        self.work=self.db.create_work("残卷","谱系测试",self.owner)
        self.a=self.db.add_witness(self.work,"甲本","version","馆藏胶片")
        self.b=self.db.add_witness(self.work,"乙本","fragment","残片")
        self.c=self.db.add_witness(self.work,"丙本","transcription","过录本")
        self.d=self.db.add_witness(self.work,"丁本","version","来源待考")
        self.db.grant_witness_editor(self.b,self.editor,self.owner)
        self.db.grant_work_access(self.work,self.reviewer,"view",self.owner)
    def tearDown(self): self.db.close(); os.unlink(self.path)
    def _register_chain(self):
        self.db.set_witness_parent(self.b,self.a,"行款一致，据甲本抄",self.owner)
        self.db.set_witness_parent(self.c,self.b,"文字承袭乙本",self.owner)
    def test_register_parent_lineage_descriptor(self):
        info=self.db.set_witness_parent(self.b,self.a,"行款一致，据甲本抄",self.owner)
        self.assertEqual(info["parent_id"],self.a)
        self.assertEqual(info["generation"],1)
        self.assertEqual(info["ancestor_chain"],["甲本","乙本"])
        self.assertFalse(info["is_archetype"])
        root=self.db._lineage_descriptor(self.a)
        self.assertEqual(root["generation"],0); self.assertTrue(root["is_archetype"]); self.assertIsNone(root["parent_id"])
    def test_self_parent_and_empty_basis_rejected(self):
        with self.assertRaisesRegex(DomainError,"不能以自己"):
            self.db.set_witness_parent(self.a,self.a,"自指",self.owner)
        with self.assertRaisesRegex(DomainError,"承传依据"):
            self.db.set_witness_parent(self.b,self.a,"  ",self.owner)
    def test_cycle_rejected_returns_conflict_witness(self):
        self._register_chain()
        try:
            self.db.set_witness_parent(self.a,self.c,"让甲本反据丙本",self.owner)
        except DomainError as exc:
            self.assertEqual(exc.extra["conflict_witness"]["id"],self.a)
            self.assertEqual(exc.extra["conflict_witness"]["siglum"],"甲本")
        else:
            self.fail("绕回自身的祖先链应当拒绝")
        # 被拒绝后旧关系不变：乙本仍以甲本为父
        self.assertEqual(self.db._lineage_descriptor(self.b)["parent_id"],self.a)
    def test_reparent_and_clear_recompute_generations(self):
        self._register_chain()
        self.assertEqual(self.db._lineage_descriptor(self.c)["generation"],2)
        self.assertEqual(self.db._lineage_descriptor(self.c)["ancestor_chain"],["甲本","乙本","丙本"])
        # 改选：乙本改据丁本，丙本世代与祖先链随之重算
        self.db.set_witness_parent(self.b,self.d,"校订后改依丁本",self.owner)
        b=self.db._lineage_descriptor(self.b); c=self.db._lineage_descriptor(self.c)
        self.assertEqual(b["ancestor_chain"],["丁本","乙本"]); self.assertEqual(c["generation"],2)
        self.assertEqual(c["ancestor_chain"],["丁本","乙本","丙本"])
        # 撤回：乙本回到无父祖本，丙本世代下降，甲本不再在链中
        self.db.clear_witness_parent(self.b,self.owner)
        b=self.db._lineage_descriptor(self.b); c=self.db._lineage_descriptor(self.c)
        self.assertTrue(b["is_archetype"]); self.assertEqual(b["generation"],0)
        self.assertEqual(c["generation"],1); self.assertEqual(c["ancestor_chain"],["乙本","丙本"])
    def test_cross_work_parent_rejected(self):
        other=self.db.create_work("别集","另一作品",self.owner)
        foreign=self.db.add_witness(other,"别集甲","version")
        with self.assertRaisesRegex(DomainError,"同一作品"):
            self.db.set_witness_parent(self.b,foreign,"跨作品承袭",self.owner)
    def test_permission_required(self):
        with self.assertRaisesRegex(DomainError,"无权"):
            self.db.set_witness_parent(self.b,self.a,"审阅尝试登记",self.reviewer)
        with self.assertRaisesRegex(DomainError,"无权"):
            self.db.set_witness_parent(self.a,self.b,"外部尝试登记",self.outsider)
        # 子本的授权编辑可以登记自己负责版本的父本
        self.db.set_witness_parent(self.b,self.a,"编辑确认承袭",self.editor)
    def test_collation_export_lists_chains_generations_and_common_ancestor(self):
        self._register_chain()
        self.db.set_witness_parent(self.d,self.a,"丁本同出甲本",self.owner)
        p1=self.db.add_passage(self.work,"第一节","春水东流。",self.owner)
        self.db.align_passage(p1,self.a,"春水东流。",1,self.owner)
        self.db.align_passage(p1,self.b,"春水[缺页]",2,self.owner)
        p2=self.db.add_passage(self.work,"第二节","故人南去。",self.owner)
        self.db.align_passage(p2,self.b,"故人南去。",1,self.owner)
        self.db.align_passage(p2,self.d,"故人南去。",2,self.owner)
        # 两个独立谱系的版本对齐同一段：无共同祖本
        p3=self.db.add_passage(self.work,"第三节","秋风西起。",self.owner)
        orphan=self.db.add_witness(self.work,"孤本","version")
        self.db.align_passage(p3,self.a,"秋风西起。",1,self.owner)
        self.db.align_passage(p3,orphan,"秋风西起。",2,self.owner)
        exported=self.db.export_collation(self.work,self.reviewer)
        by_label={p["label"]:p for p in exported["passages"]}
        a1=next(x for x in by_label["第一节"]["alignments"] if x["witness_id"]==self.a)
        b1=next(x for x in by_label["第一节"]["alignments"] if x["witness_id"]==self.b)
        self.assertEqual(a1["generation"],0); self.assertEqual(b1["generation"],1)
        self.assertEqual(b1["ancestor_chain"],["甲本","乙本"])
        self.assertEqual(by_label["第一节"]["common_ancestor_siglum"],"甲本")
        # 分叉两支：乙本、丁本同出于甲本
        self.assertEqual(by_label["第二节"]["common_ancestor_siglum"],"甲本")
        self.assertIsNone(by_label["第三节"]["common_ancestor_siglum"])
    def test_snapshot_marks_unregistered_witnesses(self):
        self._register_chain()
        snap=self.db.snapshot()
        by_id={w["id"]:w for w in snap["witnesses"]}
        self.assertIsNone(by_id[self.d]["parent_id"])
        self.assertEqual(by_id[self.b]["parent_id"],self.a)
        self.assertEqual(by_id[self.b]["parent_basis"],"行款一致，据甲本抄")
        self.assertEqual({r["witness_id"] for r in snap["witness_parents"]},{self.b,self.c})

if __name__=="__main__": unittest.main()

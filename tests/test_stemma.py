import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import CollationDB, DomainError

class StemmaTest(unittest.TestCase):
    def setUp(self):
        fd,self.path=tempfile.mkstemp(suffix=".db"); os.close(fd); self.db=CollationDB(self.path)
        self.owner=self.db.add_user("负责人","owner"); self.editor=self.db.add_user("编辑","editor")
        self.work=self.db.create_work("残卷","谱系测试",self.owner)
        # 甲（祖本）→ 乙 → 丙；丁与戊暂不登记来源
        self.a=self.db.add_witness(self.work,"甲本","version","胶片")
        self.b=self.db.add_witness(self.work,"乙本","fragment","残片")
        self.c=self.db.add_witness(self.work,"丙抄","transcription","抄本")
        self.d=self.db.add_witness(self.work,"丁本","version")
        self.e=self.db.add_witness(self.work,"戊本","version")
        self.db.grant_witness_editor(self.b,self.editor,self.owner)
        self.db.grant_witness_editor(self.c,self.editor,self.owner)
        self.passage=self.db.add_passage(self.work,"第一节","春水东流。",self.owner)
        self.db.align_passage(self.passage,self.a,"春水东流。",1,self.owner)
        self.db.align_passage(self.passage,self.b,"春水[缺页]",2,self.owner)
        self.db.align_passage(self.passage,self.c,"春水东流。",3,self.owner)

    def tearDown(self): self.db.close(); os.unlink(self.path)

    def test_root_parent_chain_and_single_parent(self):
        self.db.set_lineage(self.a,None,"定为祖本",self.owner)
        self.db.set_lineage(self.b,self.a,"行款同甲本",self.owner)
        self.db.set_lineage(self.c,self.b,"据乙本转抄",self.editor)
        report=self.db.lineage_report(self.work,self.owner)
        by={w["siglum"]:w for w in report["witnesses"]}
        self.assertEqual([x["siglum"] for x in by["丙抄"]["ancestor_chain"]],["丙抄","乙本","甲本"])
        self.assertEqual(by["丙抄"]["generation"],2)
        self.assertTrue(by["甲本"]["is_root"]); self.assertEqual(by["甲本"]["generation"],0)
        self.assertEqual([x["siglum"] for x in self._unregistered(report)],["丁本","戊本"])
        # 每个子本最多一个父本：改选即覆盖旧关系
        self.db.set_lineage(self.c,self.a,"复核后认定直接据甲本",self.editor)
        report=self.db.lineage_report(self.work,self.owner)
        by={w["siglum"]:w for w in report["witnesses"]}
        self.assertEqual(by["丙抄"]["parent_id"],self.a)
        self.assertEqual(by["丙抄"]["generation"],1)
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM witness_stemma").fetchone()[0],3)

    def test_cycle_rejected_with_conflict_versions(self):
        self.db.set_lineage(self.a,None,"祖本",self.owner)
        self.db.set_lineage(self.b,self.a,"据甲本",self.owner)
        self.db.set_lineage(self.c,self.b,"据乙本",self.owner)
        try:
            self.db.set_lineage(self.a,self.c,"试图让祖本反据丙抄",self.owner)
            self.fail("应当拒绝成环关系")
        except DomainError as exc:
            self.assertIn("绕回",str(exc))
            self.assertEqual(exc.details["conflict_witness_ids"],[self.a,self.c,self.b])
            self.assertEqual(exc.details["conflict_chain"],["甲本","丙抄","乙本","甲本"])
        # 拒绝后旧关系保持不变
        row=self.db.conn.execute("SELECT parent_id,is_root FROM witness_stemma WHERE witness_id=?",(self.a,)).fetchone()
        self.assertIsNone(row["parent_id"]); self.assertEqual(row["is_root"],1)
        # 自指也拒绝
        try:
            self.db.set_lineage(self.b,self.b,"自为父本",self.owner)
            self.fail("应当拒绝自指关系")
        except DomainError as exc:
            self.assertEqual(exc.details["conflict_chain"],["乙本","乙本"])

    def test_withdraw_and_reparent_recompute(self):
        self.db.set_lineage(self.a,None,"祖本",self.owner)
        self.db.set_lineage(self.b,self.a,"据甲本",self.owner)
        self.db.set_lineage(self.c,self.b,"据乙本",self.owner)
        self.db.withdraw_lineage(self.b,self.owner)
        report=self.db.lineage_report(self.work,self.owner)
        by={w["siglum"]:w for w in report["witnesses"]}
        self.assertFalse(by["乙本"]["registered"])
        self.assertEqual([x["siglum"] for x in by["丙抄"]["ancestor_chain"]],["丙抄","乙本"])
        self.assertEqual(by["丙抄"]["generation"],1)
        # 重新接上：丁本为新祖本，乙据丁，世代与共同祖本重算
        self.db.set_lineage(self.d,None,"更早刻本",self.owner)
        self.db.set_lineage(self.b,self.d,"据丁本",self.owner)
        report=self.db.lineage_report(self.work,self.owner)
        by={w["siglum"]:w for w in report["witnesses"]}
        self.assertEqual(by["丙抄"]["generation"],2)
        self.assertEqual([x["siglum"] for x in by["丙抄"]["ancestor_chain"]],["丙抄","乙本","丁本"])

    def test_collation_export_genealogy(self):
        self.db.set_lineage(self.a,None,"祖本",self.owner)
        self.db.set_lineage(self.b,self.a,"据甲本",self.owner)
        self.db.set_lineage(self.c,self.b,"据乙本",self.owner)
        exported=self.db.export_collation(self.work,self.owner)
        g=exported["passages"][0]["genealogy"]
        self.assertEqual(g["common_ancestor"]["siglum"],"甲本")
        gens={w["siglum"]:w["generation"] for w in g["witnesses"]}
        self.assertEqual(gens,{"甲本":0,"乙本":1,"丙抄":2})
        b=[w for w in g["witnesses"] if w["siglum"]=="乙本"][0]
        self.assertEqual([x["siglum"] for x in b["ancestor_chain"]],["乙本","甲本"])
        # 戊本未登记来源，若进入段落则共同祖本为空
        self.db.align_passage(self.passage,self.e,"春水东流。",4,self.owner)
        exported=self.db.export_collation(self.work,self.owner)
        self.assertIsNone(exported["passages"][0]["genealogy"]["common_ancestor"])

    def test_cross_work_basis_and_permission(self):
        other=self.db.create_work("别集","",self.owner)
        foreign=self.db.add_witness(other,"异本","version")
        with self.assertRaisesRegex(DomainError,"同一作品"):
            self.db.set_lineage(self.b,foreign,"跨作品",self.owner)
        with self.assertRaisesRegex(DomainError,"依据"):
            self.db.set_lineage(self.b,self.a,"",self.owner)
        with self.assertRaisesRegex(DomainError,"无权"):
            self.db.set_lineage(self.d,self.a,"编辑改未授权版本",self.editor)
        with self.assertRaisesRegex(DomainError,"无权"):
            self.db.withdraw_lineage(self.d,self.editor)
        # 已授权版本的编辑可以登记谱系，也可以撤回
        self.db.set_lineage(self.b,self.a,"据甲本",self.editor)
        self.db.withdraw_lineage(self.b,self.editor)

    @staticmethod
    def _unregistered(report):
        return report["unregistered"]

if __name__=="__main__": unittest.main()

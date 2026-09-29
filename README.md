# 数字人文文本校勘

这是一个 Python 标准库实现的校勘工作台，使用 SQLite 保存作品、版本、残片、转录、段落、异文、注释、修订层和快照，并通过 `http.server` 暴露 JSON API。

## 启动与测试

```bash
python app.py
python -m unittest discover -s tests -v
```

默认端口 `8114`，地址 <http://127.0.0.1:8114>。首次启动创建一个带缺页残片和不可辨标记的示例。数据库可通过 `COLLATION_DB` 指定，端口可通过 `PORT` 指定。

## 业务规则

- 版本类型限定为 `version`、`fragment`、`transcription`。
- 段落和版本必须属于同一作品，同一版本不能重复对齐同一段落。
- 只有负责人或被单独授权的编辑可以修改对应版本；其他用户只有查看权限。
- `[缺页]`、`[不可辨]`、`[残损]` 等标记会参与校勘稿导出和缺口统计，不匹配的方括号会拒绝保存。
- 每次新增或修改异文都会产生递增修订号和 JSON 快照；提交必须携带 `expected_revision`，旧页面不能覆盖新层。
- 锁定段落由负责人执行，锁定后任何新修订都会被拒绝。
- 版本谱系：同一作品中每个版本最多登记一个父本并记录承传依据，父本留空即定为祖本；未登记来源的版本单独列出。新增或改选父本时若祖先链绕回自身则拒绝，错误体随附冲突版本环（`conflict_witness_ids`、`conflict_chain`）。撤回关系或换父本后，后代世代与共同祖本实时重算。

## 主要接口

- `POST /api/users`、`POST /api/works`
- `POST /api/works/{id}/witnesses`、`POST /api/witnesses/{id}/editors`
- `POST /api/works/{id}/passages`、`POST /api/works/{id}/access`
- `GET /api/works/{id}/stemma?user_id=...`：版本谱系（祖先链、世代、祖本、未登记来源）
- `POST /api/witnesses/{id}/lineage`：建/改父本关系（`parent_id` 为空表示祖本，需 `basis`、`user_id`）
- `POST /api/witnesses/{id}/lineage/withdraw`：撤回已登记的来源关系
- `POST /api/alignments`
- `POST /api/variants`、`POST /api/variants/{id}/revisions`
- `GET /api/passages/{id}/snapshots/{revision}?user_id=...`
- `POST /api/passages/{id}/lock`
- `GET /api/works/{id}/collation?user_id=...`

导出接口把版本对齐、异文、注释、残损缺口、锁定状态以及每段的祖先链、世代和共同祖本（`genealogy`）组合成可复核的校勘稿。

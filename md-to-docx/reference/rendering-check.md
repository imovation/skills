# 渲染验证方法（docx → PDF 逐页检查）

docx 结构正确不代表排版正确（孤行标题、清单跨页、图片下沉只能靠渲染发现）。
组装/格式化完成后按以下步骤验证：

## 1. 转 PDF（LibreOffice 无头模式）

```bash
soffice --headless --convert-to pdf 文书.docx --outdir /tmp/render
```

## 2. 页数与页面尺寸

```bash
pdfinfo /tmp/render/文书.pdf | grep -E "Pages|Page size"
```

- A4 应为 `595.304 x 841.89 pts`；不是 A4 说明页面未设置。
- 页数应与预期一致（正文 + 目录 + 附件页数）。

## 3. 逐页检查标题与图片是否同页（防孤行）

```bash
# 每页是否有附件标题
for i in $(seq 4 $(pdfinfo 文书.pdf | grep Pages | awk '{print $2}')); do
  t=$(pdftotext -f $i -l $i 文书.pdf - | grep -o "附件 [0-9]：" | head -1)
  n=$(pdfimages -list 文书.pdf 2>/dev/null | awk -v p=$i '$1==p' | wc -l)
  [ -n "$t" ] && echo "页$i: $t 图数=$n"
done
```

- 标题页图数必须 ≥1（标题与首图同页）；图数=0 的标题页 = 孤行，需调低图片限高。

## 4. 检查目录/清单是否完整一页

```bash
pdftotext -f N -l N 文书.pdf - | grep -c "附件"
```

- 目录页应完整列出全部附件项，不得跨页拆分。

## 5. 全文残留检查

```bash
pdftotext 文书.pdf - | grep -n "旧日期\|旧金额\|【填写】"
```

- 确认无旧版本日期/金额残留；【填写】占位符应为计划保留项。

import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = "data/raw/Vivayu dataset tomato.xlsx";
const previewPath = "reports/raw-workbook-preview.png";

const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const summary = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 8_000,
  tableMaxRows: 12,
  tableMaxCols: 18,
  tableMaxCellChars: 120,
});

console.log(summary.ndjson);

const sheet = workbook.worksheets.getItemAt(0);
const usedRange = sheet.getUsedRange();
const values = usedRange.values;

console.log(`\nSheet: ${sheet.name}`);
console.log(`Rows: ${values.length}`);
console.log(`Columns: ${Math.max(...values.map((row) => row.length))}`);

for (const rowNumber of [1, 2, 3, 4, 65, 66, 67, 130, 131, 132, 200, 260, 320, 363]) {
  const row = values[rowNumber - 1];
  if (row) {
    console.log(`Row ${rowNumber}: ${JSON.stringify(row)}`);
  }
}

const preview = await workbook.render({
  sheetName: sheet.name,
  range: "A1:R80",
  scale: 1,
  format: "png",
});

await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
console.log(`\nPreview saved to ${previewPath}`);

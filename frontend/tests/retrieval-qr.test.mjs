import assert from "node:assert/strict";
import test from "node:test";
import QRCode from "qrcode";
import { PNG } from "pngjs";
import { BinaryBitmap, HybridBinarizer, QRCodeReader, RGBLuminanceSource } from "@zxing/library";
import { retrievalQrFilename, retrievalQrOptions } from "../libs/retrieval/qr.ts";

test("the downloaded QR PNG contains the exact versioned backend payload", async () => {
  const payload = `SAULI:RETRIEVAL:v1:${"A".repeat(43)}`;
  const pngBytes = await QRCode.toBuffer(payload, retrievalQrOptions);
  const image = PNG.sync.read(pngBytes);
  const luminance = new Uint8ClampedArray(image.width * image.height);
  for (let i = 0; i < luminance.length; i++) {
    luminance[i] = (image.data[i * 4] + 2 * image.data[i * 4 + 1] + image.data[i * 4 + 2]) / 4;
  }
  const bitmap = new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(luminance, image.width, image.height)));
  assert.equal(new QRCodeReader().decode(bitmap).getText(), payload);
  assert.equal(retrievalQrFilename, "SAULI-Retrieval-QR.png");
  assert.equal(pngBytes.subarray(1, 4).toString(), "PNG");
});

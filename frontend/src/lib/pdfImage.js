/**
 * Render the first page of a PDF to an image the OCR engine can read.
 *
 * People are handed their documents in whatever format the issuing office used,
 * so a scanned ID arrives as a PDF about as often as it arrives as a photo.
 * Rendering happens in the browser, so the document never leaves the device,
 * which is the same guarantee the photo path makes.
 */

// A higher scale means a larger canvas and noticeably better OCR accuracy on
// small print, at the cost of a little time. 2.5 is a reasonable middle.
const RENDER_SCALE = 2.5;

export async function pdfFirstPageToBlob(file) {
  const pdfjs = await import("pdfjs-dist");

  // The worker is bundled alongside the library; pointing at it explicitly
  // avoids pdf.js trying to fetch a copy from a CDN at runtime.
  const workerSrc = (await import("pdfjs-dist/build/pdf.worker.min.mjs?url")).default;
  pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;

  const buffer = await file.arrayBuffer();
  const doc = await pdfjs.getDocument({ data: buffer }).promise;

  try {
    const page = await doc.getPage(1);
    const viewport = page.getViewport({ scale: RENDER_SCALE });

    const canvas = document.createElement("canvas");
    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);

    const context = canvas.getContext("2d");
    // Scanned pages often have transparent regions; without a white base these
    // render black and the OCR engine reads nothing.
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);

    await page.render({ canvasContext: context, viewport, canvas }).promise;

    return await new Promise((resolve, reject) => {
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error("Could not render the page."))),
        "image/png"
      );
    });
  } finally {
    doc.destroy();
  }
}

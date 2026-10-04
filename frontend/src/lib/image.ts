export const PHOTO_MAX_BYTES = 5 * 1024 * 1024 // contract: photo up to 5 MB
export const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const MAX_SIDE = 2560

/**
 * Makes a phone photo fit the 5 MB limit: files already small enough go as they are, bigger ones are scaled down
 * (longest side 2560 px) and re-encoded as JPEG in the browser.
 */
export async function fitForUpload(file: File): Promise<File> {
  if (file.size <= PHOTO_MAX_BYTES * 0.8) return file
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85))
  if (!blob) throw new Error('Nie udało się przygotować zdjęcia.')
  return new File([blob], file.name.replace(/\.\w+$/, '') + '.jpg', { type: 'image/jpeg' })
}

// aladin-lite ships no TypeScript types; this is a minimal shim. The API we use:
//   A.init: Promise<void>
//   A.aladin(el, options) -> aladin instance
//   A.image(url, { wcs, name, successCallback, errorCallback }) -> image layer
//   aladin.setOverlayImageLayer(image, name)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare module "aladin-lite" {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const A: any;
  export default A;
}

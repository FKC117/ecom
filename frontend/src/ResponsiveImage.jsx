export default function ResponsiveImage({media,src,sizes='100vw',...props}) {
  return <img {...props} src={media?.src||src} srcSet={media?.srcset||undefined} sizes={media?.srcset?sizes:undefined} width={media?.width||undefined} height={media?.height||undefined} />
}

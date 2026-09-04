import type { MetadataRoute } from 'next';
import { absoluteSiteUrl, siteUrl } from '@/app/lib/site-url';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
    },
    sitemap: absoluteSiteUrl('/sitemap.xml'),
    host: siteUrl.origin,
  };
}

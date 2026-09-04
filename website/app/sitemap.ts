import type { MetadataRoute } from 'next';
import { absoluteSiteUrl } from '@/app/lib/site-url';
import { tasks } from '@/app/lib/tasks';

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: absoluteSiteUrl('/') },
    ...tasks.map((task) => ({
      url: absoluteSiteUrl(`/tasks/${task.slug}`),
    })),
  ];
}

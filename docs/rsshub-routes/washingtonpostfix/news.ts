import type { Data, Route } from '@/types';
import ofetch from '@/utils/ofetch';
import parser from '@/utils/rss-parser';

export const route: Route = {
    path: '/news', categories: ['traditional-media'], example: '/washingtonpostfix/news',
    features: { requireConfig: false, requirePuppeteer: false, antiCrawler: false, supportBT: false, supportPodcast: false, supportScihub: false },
    name: 'News', maintainers: ['8cli'], handler, url: 'https://feeds.washingtonpost.com/rss/world',
};

async function handler(): Promise<Data> {
    const xml = await ofetch('https://feeds.washingtonpost.com/rss/world', { parseResponse: (t: string) => t });
    const feed = await parser.parseString(xml);
    return { title: feed.title ?? 'Washington Post', link: feed.link ?? 'https://www.washingtonpost.com/', item: feed.items.map((i) => ({ title: i.title, link: i.link, pubDate: i.pubDate, author: i.creator })) };
}

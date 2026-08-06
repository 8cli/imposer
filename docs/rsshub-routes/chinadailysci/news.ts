import type { Data, Route } from '@/types';
import parser from '@/utils/rss-parser';

export const route: Route = {
    path: '/news',
    categories: ['traditional-media'],
    example: '/chinadailysci/news',
    features: {
        requireConfig: false, requirePuppeteer: false, antiCrawler: false,
        supportBT: false, supportPodcast: false, supportScihub: false,
    },
    name: 'News',
    maintainers: ['8cli'],
    handler,
    url: 'https://www.chinadaily.com.cn/rss/china_rss.xml',
};

async function handler(): Promise<Data> {
    const feed = await parser.parseURL('https://www.chinadaily.com.cn/rss/china_rss.xml');
    return {
        title: feed.title ?? 'China Daily Sci',
        link: feed.link ?? 'https://www.chinadaily.com.cn/rss/china_rss.xml',
        item: feed.items.map((i) => ({
            title: i.title,
            link: i.link,
            pubDate: i.pubDate,
            author: i.creator,
        })),
    };
}

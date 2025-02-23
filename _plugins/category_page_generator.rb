# Create this file as _plugins/category_page_generator.rb
module Jekyll
    class CategoryPageGenerator < Generator
      safe true
  
      def generate(site)
        site.categories.each do |category, posts|
          site.pages << CategoryPage.new(site, site.source, category, posts)
        end
      end
    end
  
    class CategoryPage < Page
      def initialize(site, base, category, posts)
        @site = site
        @base = base
        @dir = File.join('category', category.downcase)
        @name = 'index.html'
  
        self.process(@name)
        self.read_yaml(File.join(base, '_layouts'), 'category.html')
        self.data['title'] = category
        self.data['category'] = category
        self.data['posts'] = posts
      end
    end
  end# Create this file as _plugins/category_page_generator.rb
  module Jekyll
    class CategoryPageGenerator < Generator
      safe true
  
      def generate(site)
        site.categories.each do |category, posts|
          site.pages << CategoryPage.new(site, site.source, category, posts)
        end
      end
    end
  
    class CategoryPage < Page
      def initialize(site, base, category, posts)
        @site = site
        @base = base
        @dir = File.join('category', category.downcase)
        @name = 'index.html'
  
        self.process(@name)
        self.read_yaml(File.join(base, '_layouts'), 'category.html')
        self.data['title'] = category
        self.data['category'] = category
        self.data['posts'] = posts
      end
    end
  end
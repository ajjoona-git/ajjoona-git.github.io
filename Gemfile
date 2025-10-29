# frozen_string_literal: true

source "https://rubygems.org"

# GitHub Actions 및 Jekyll이 플러그인을 인식하도록 그룹으로 묶습니다.
group :jekyll_plugins do
  gem "jekyll-theme-chirpy", "~> 7.4", ">= 7.4.1" # 기존 테마 (그룹 안으로 이동)
  gem "jekyll-polyglot"                           # (추가) 6.2. 11단계에서 요청한 플러그인
end

gem "html-proofer", "~> 5.0", group: :test

platforms :mingw, :x64_mingw, :mswin, :jruby do
  gem "tzinfo", ">= 1", "< 3"
  gem "tzinfo-data"
end

gem "wdm", "~> 0.2.0", :platforms => [:mingw, :x64_mingw, :mswin]
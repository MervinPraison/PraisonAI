class Praisonai < Formula
    include Language::Python::Virtualenv
  
    desc "AI tools for various AI applications"
    homepage "https://github.com/MervinPraison/PraisonAI"
    url "https://github.com/MervinPraison/PraisonAI/archive/refs/tags/2.0.42.tar.gz"
    sha256 "1828fb9227d10f991522c3f24f061943a254b667196b40b1a3e4a54a8d30ce32"  # Replace with actual SHA256 checksum
    license "MIT"
  
    depends_on "python@3.9"
  
    def install
      virtualenv_install_with_resources
    end
  
    test do
      system "#{bin}/praisonai", "--version"
    end
  end
  
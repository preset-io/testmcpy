class Testmcpy < Formula
  include Language::Python::Virtualenv

  desc "MCP Testing Framework - Test LLM tool calling with MCP services"
  homepage "https://github.com/preset-io/testmcpy"
  url "https://files.pythonhosted.org/packages/75/cc/5f97a2cacd242bcb89e6a85a6ac76c64c680460919c1b75198654d358a54/testmcpy-0.11.10.tar.gz"
  sha256 "8c336cdb5450cfac4fb46b27160af89e7d19d24195f048060e56941f7108a84a"
  license "Apache-2.0"

  depends_on "python@3.11"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "MCP Testing Framework", shell_output("#{bin}/testmcpy --help")
  end
end

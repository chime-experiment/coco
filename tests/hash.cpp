#include <iostream>
#include <openssl/md5.h>

#include "json.hpp"

using json = nlohmann::json;

std::string get_md5sum(json config) {
    unsigned char md5sum[MD5_DIGEST_LENGTH];

    std::vector<std::uint8_t> v_msgpack = json::to_msgpack(config);
    MD5((const unsigned char*)v_msgpack.data(), v_msgpack.size(), md5sum);

    char md5str[33];
    for (int i = 0; i < 16; i++)
        sprintf(&md5str[i * 2], "%02x", (unsigned int)md5sum[i]);

    return std::string(md5str);
}

int main(int argc, char** argv) {
	json config = json::parse(argv[1]);

    std::string hash = get_md5sum(config);

	std::cout << hash << std::endl;
	return 0;
}

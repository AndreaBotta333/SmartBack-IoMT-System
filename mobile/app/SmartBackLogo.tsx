import React from "react";
import { Image, StyleSheet } from "react-native";

export function SmartBackLogo({ large = false }: { large?: boolean }) {
  return (
    <Image
      accessibilityLabel="SmartBack"
      resizeMode="contain"
      source={large ? require("./assets/smartback-logo-login.png") : require("./assets/smartback-logo-transparent.png")}
      style={large ? styles.large : styles.compact}
    />
  );
}

const styles = StyleSheet.create({
  large: { width: 286, height: 197 },
  compact: { width: 58, height: 58 },
});
